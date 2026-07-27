"""AgentClinic harness adapter.

AgentClinic is OSCE-style: a Doctor agent iteratively queries a Patient agent
(LLM-simulated from a scenario) and may request lab tests from a Measurement
agent until "DIAGNOSIS READY: <name>" or the inference budget is exhausted.

For our rare-disease benchmark we cannot construct a full OSCE scenario from
a CanonicalCase (we lack a patient-actor persona and lab-result table). The
shim therefore drives AgentClinic in a "scenario-on-the-fly" mode:

1. Build a MedQA-style OSCE scenario from the CanonicalCase (HPO terms become
   Patient_Actor.Symptoms, gold disease becomes Correct_Diagnosis).
2. Write a one-line `agentclinic_medqa.jsonl` into a temp working directory.
3. Run `agents/agentclinic/.venv/bin/python agentclinic.py` from that
   directory with `--agent_dataset MedQA --num_scenarios 1`.
4. Parse stdout dialogue to recover the Doctor's diagnosis (and any earlier
   differential mentions) plus the moderator verdict.
5. The Doctor only emits ONE final diagnosis — to satisfy the harness's
   top-5 contract we additionally fire a single follow-up LLM call (still via
   AgentClinic's venv) that asks for a ranked DDx given the dialogue history.

The Doctor's single diagnosis populates rank 1; the follow-up call fills
ranks 2..5. Both are mapped to ORPHA IDs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
import uuid
from pathlib import Path
from typing import List, Optional

from harness.agents._adapter_utils import (
    PROJECT_ROOT,
    case_to_question,
    estimate_tokens,
    fill_cost_from_tokens,
    hpo_terms_to_text,
    load_dotenv,
    map_names_to_ids,
    map_names_to_ids_with_variants,
    max_tokens_floor_for_backbone,
    parse_ranked_top5,
    reasoning_disabled_for_backbone,
    reasoning_effort_for_backbone,
    resolve_llm_gateway,
)
from harness.agents.base import AgentAdapter
from harness.canonical_case import CanonicalCase
from harness.logging.schema import CostBreakdown, EvalMode, Pillar, PredictionLog


AGENTCLINIC_ROOT = PROJECT_ROOT / "agents" / "agentclinic"
AGENTCLINIC_PY = AGENTCLINIC_ROOT / ".venv" / "bin" / "python"
AGENTCLINIC_MAIN = AGENTCLINIC_ROOT / "agentclinic.py"


# Stdout dialogue parsers — match the exact print formats used by main():
#   print("Doctor [{x}%]:", doctor_dialogue)
#   print("Patient [{x}%]:", pi_dialogue)
#   print("Measurement [{x}%]:", pi_dialogue)
#   print("Correct answer:", scenario.diagnosis_information())
#   print("Scene {i}, The diagnosis was ", "CORRECT"|"INCORRECT", ...)
_DOC_RE = re.compile(r"^Doctor \[(\d+)%\]:\s*(.*)$")
_PAT_RE = re.compile(r"^Patient \[(\d+)%\]:\s*(.*)$")
_MEAS_RE = re.compile(r"^Measurement \[(\d+)%\]:\s*(.*)$")
_DIAG_RE = re.compile(r"DIAGNOSIS READY:\s*(.+?)(?:\.|$)", re.IGNORECASE)
_VERDICT_RE = re.compile(r"The diagnosis was\s+(CORRECT|INCORRECT)")


def _build_scenario(case: CanonicalCase) -> dict:
    """Project CanonicalCase -> AgentClinic OSCE-MedQA scenario_dict."""
    demo = case.demographics
    age = (
        f"{int(demo.age_at_onset_years)}-year-old"
        if demo and demo.age_at_onset_years is not None
        else "adult"
    )
    sex = demo.sex if demo and demo.sex else "patient"
    demographics = f"{age} {sex}".strip()

    hpo_text = hpo_terms_to_text(case.gold_hpo_terms) if case.gold_hpo_terms else ""
    history = (
        case.free_text_vignette
        or case.synthetic_vignette
        or (
            "Patient presents with the following HPO-coded clinical features: "
            + (hpo_text or "no phenotype info available.")
        )
    )

    primary = "Multiple clinical findings"
    secondary: List[str] = []
    if case.gold_hpo_terms:
        labels = [t.label or t.id for t in case.gold_hpo_terms if not t.negated]
        if labels:
            primary = labels[0]
            secondary = labels[1:8]

    correct_dx = (
        case.gold_label.disease_name
        or case.gold_label.omim_id
        or case.gold_label.orphanet_id
        or case.gold_label.ccrd_id
        or "Unknown"
    )

    return {
        "OSCE_Examination": {
            "Objective_for_Doctor": (
                "Identify the most likely rare disease that explains the "
                "patient's constellation of findings."
            ),
            "Patient_Actor": {
                "Demographics": demographics,
                "History": history,
                "Symptoms": {
                    "Primary_Symptom": primary,
                    "Secondary_Symptoms": secondary,
                },
                "Past_Medical_History": "Not otherwise specified.",
                "Social_History": "Not otherwise specified.",
                "Review_of_Systems": "Per HPO list.",
            },
            "Physical_Examination_Findings": {
                "Vital_Signs": {"Notes": "Not otherwise specified."},
                "General": (
                    "Phenotypic features per HPO list: " + (hpo_text or "n/a")
                ),
            },
            "Test_Results": {
                "Available_Genetic_Workup": (
                    "Not detailed; respond NORMAL READINGS if asked for "
                    "tests not consistent with this rare disease presentation."
                ),
            },
            "Correct_Diagnosis": correct_dx,
        }
    }


def _parse_dialogue(stdout: str) -> dict:
    """Pull dialogue turns + final diagnosis + verdict from agentclinic stdout."""
    doctor_turns: List[str] = []
    patient_turns: List[str] = []
    measurement_turns: List[str] = []
    final_dx: Optional[str] = None
    verdict: Optional[str] = None
    correct_dx: Optional[str] = None
    n_inferences = 0

    current: Optional[List[str]] = None
    for line in stdout.splitlines():
        if (m := _DOC_RE.match(line)):
            n_inferences += 1
            text = m.group(2)
            doctor_turns.append(text)
            current = doctor_turns
            if (mdiag := _DIAG_RE.search(text)):
                final_dx = mdiag.group(1).strip()
        elif (m := _PAT_RE.match(line)):
            patient_turns.append(m.group(2))
            current = patient_turns
        elif (m := _MEAS_RE.match(line)):
            measurement_turns.append(m.group(2))
            current = measurement_turns
        elif line.startswith("Correct answer:"):
            correct_dx = line.split("Correct answer:", 1)[1].strip()
            current = None
        elif (m := _VERDICT_RE.search(line)):
            verdict = m.group(1)
            current = None
        elif current is not None and line.strip():
            # Multi-line dialogue continuation
            current[-1] = current[-1] + " " + line.strip()

    # Sometimes diagnosis appears without "DIAGNOSIS READY" — fall back to
    # the last doctor turn.
    if final_dx is None and doctor_turns:
        # Look for phrasing like "most likely diagnosis is X" / "diagnosis: X"
        last = doctor_turns[-1]
        for pat in [
            r"diagnosis\s+is[: ]\s*([A-Z][^.]+)",
            r"most likely[: ]\s*([A-Z][^.]+)",
        ]:
            mm = re.search(pat, last, re.IGNORECASE)
            if mm:
                final_dx = mm.group(1).strip()
                break

    return {
        "doctor_turns": doctor_turns,
        "patient_turns": patient_turns,
        "measurement_turns": measurement_turns,
        "final_dx": final_dx,
        "verdict": verdict,
        "correct_dx": correct_dx,
        "n_inferences": n_inferences,
    }


# Follow-up DDx driver: takes the dialogue + final dx, returns a free-text top-5.
_FOLLOWUP_DRIVER = textwrap.dedent(
    r"""
    import json, os, sys, traceback
    sys.path.insert(0, os.getcwd())
    # Reuse agentclinic.query_model — it already has the OpenRouter branch wired.
    try:
        import agentclinic as ac
    except Exception as e:
        print(json.dumps({"error": "import_failed", "msg": str(e),
                          "tb": traceback.format_exc()}), flush=True)
        sys.exit(0)

    payload = json.loads(sys.stdin.read())
    dialogue = payload["dialogue"]
    final_dx = payload.get("final_dx") or ""
    case = payload["case_question"]

    system = (
        "You are a senior physician who, given a case and the dialogue from a "
        "doctor-patient OSCE encounter, must produce a final ranked top-5 "
        "rare-disease differential diagnosis."
    )
    prompt = (
        "Case description:\n" + case + "\n\n"
        "Doctor-patient dialogue summary:\n" + dialogue + "\n\n"
        + (f"Doctor's final stated diagnosis: {final_dx}\n\n" if final_dx else "")
        + "Produce a top-5 ranked differential, most likely first, in the format:\n"
        "1. <Disease Name>\n2. <Disease Name>\n3. <Disease Name>\n"
        "4. <Disease Name>\n5. <Disease Name>\n"
        "Use canonical Orphanet / OMIM disease names. After the list, add a "
        "two-sentence rationale."
    )
    try:
        out = ac.query_model("openrouter", prompt, system, tries=3, timeout=30.0)
    except Exception as e:
        out = f"ERROR: {e}"
    print(json.dumps({"final": out}), flush=True)
    """
).strip()


class AgentClinicAdapter(AgentAdapter):
    """AgentClinic shim. Pillar 2 primary; supports P5 reasoning trace."""

    NAME = "agentclinic"

    def __init__(
        self,
        backbone_id: str = "openrouter/google/gemini-3-flash-preview",
        backbone_temperature: float = 0.0,
        backbone_seed: Optional[int] = None,
        agent_extra: Optional[dict] = None,
    ):
        super().__init__(
            backbone_id=backbone_id,
            backbone_temperature=backbone_temperature,
            backbone_seed=backbone_seed,
            agent_extra=agent_extra,
        )
        load_dotenv()
        if backbone_id.startswith("openrouter/"):
            self._model_id = backbone_id[len("openrouter/"):]
        else:
            self._model_id = backbone_id
        ex = self.agent_extra or {}
        self._total_inferences = int(ex.get("total_inferences", 8))
        self._timeout_s = int(ex.get("timeout_s", 300))

    def supports_pillar(self, pillar: Pillar) -> bool:
        return pillar in ("P2_phenotype_ddx", "P5_reasoning_communication")

    # --------------------------------------------------------------

    def _run_osce(self, scenario: dict) -> tuple[dict, int, str]:
        """Run agentclinic.py end-to-end on a one-scenario MedQA dataset."""
        if not AGENTCLINIC_PY.exists():
            raise FileNotFoundError(
                f"AgentClinic venv python missing: {AGENTCLINIC_PY}"
            )

        sdk_base, api_key = resolve_llm_gateway()
        env = os.environ.copy()
        env["OPENROUTER_API_KEY"] = api_key
        env["OPENROUTER_BASE_URL"] = sdk_base
        env["OPENAI_API_KEY"] = api_key
        env["CANARY_BACKBONE_MODEL"] = self._model_id
        env["PYTHONUNBUFFERED"] = "1"
        # 2026-05-19 — propagate reasoning_effort=minimal for GPT-5 / o-series
        re_effort = reasoning_effort_for_backbone(self.backbone_id)
        if re_effort:
            env["OPENROUTER_REASONING_EFFORT"] = re_effort
        # 2026-07-03 — heavy reasoners that ignore reasoning_effort (V4-Pro)
        # emit unbounded reasoning that eats the doctor turn's max_tokens=200
        # → content None → 30x retry loop → timeout. The only clean lever is
        # to disable reasoning (reasoning={"enabled": false}); the max_tokens
        # floor is a secondary safety.
        if reasoning_disabled_for_backbone(self.backbone_id):
            env["OPENROUTER_REASONING_DISABLE"] = "1"
        mt_floor = max_tokens_floor_for_backbone(self.backbone_id)
        if mt_floor:
            env["OPENROUTER_MAX_TOKENS_FLOOR"] = str(mt_floor)

        # ScenarioLoaderMedQA reads './agentclinic_medqa.jsonl' from cwd —
        # run in a temp dir with our scenario and a symlink to the real .py.
        with tempfile.TemporaryDirectory(prefix="agentclinic_shim_") as td:
            tdp = Path(td)
            (tdp / "agentclinic_medqa.jsonl").write_text(
                json.dumps(scenario) + "\n", encoding="utf-8"
            )
            # agentclinic.py imports openai etc.; we run it via its venv
            # python with --num_scenarios 1.
            cmd = [
                str(AGENTCLINIC_PY),
                str(AGENTCLINIC_MAIN),
                "--openai_api_key",
                api_key or "unused",
                "--doctor_llm",
                "openrouter",
                "--patient_llm",
                "openrouter",
                "--measurement_llm",
                "openrouter",
                "--moderator_llm",
                "openrouter",
                "--agent_dataset",
                "MedQA",
                "--num_scenarios",
                "1",
                "--total_inferences",
                str(self._total_inferences),
            ]
            t0 = time.time()
            proc = subprocess.run(
                cmd,
                cwd=str(tdp),
                env=env,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
            latency_ms = int((time.time() - t0) * 1000)
            if proc.returncode != 0:
                stderr_tail = proc.stderr[-1500:] if proc.stderr else ""
                raise RuntimeError(
                    f"agentclinic.py exited {proc.returncode}: {stderr_tail}\n"
                    f"stdout tail: {proc.stdout[-800:]}"
                )
            parsed = _parse_dialogue(proc.stdout)
            return parsed, latency_ms, proc.stdout

    def _run_followup(
        self, dialogue: str, final_dx: Optional[str], case_question: str
    ) -> str:
        sdk_base, api_key = resolve_llm_gateway()
        env = os.environ.copy()
        env["OPENROUTER_API_KEY"] = api_key
        env["OPENROUTER_BASE_URL"] = sdk_base
        env["OPENAI_API_KEY"] = api_key
        env["CANARY_BACKBONE_MODEL"] = self._model_id
        env["PYTHONUNBUFFERED"] = "1"
        # 2026-05-19 — propagate reasoning_effort=minimal for GPT-5 / o-series
        re_effort = reasoning_effort_for_backbone(self.backbone_id)
        if re_effort:
            env["OPENROUTER_REASONING_EFFORT"] = re_effort
        # 2026-07-03 — heavy reasoners that ignore reasoning_effort (V4-Pro)
        # emit unbounded reasoning that eats the doctor turn's max_tokens=200
        # → content None → 30x retry loop → timeout. The only clean lever is
        # to disable reasoning (reasoning={"enabled": false}); the max_tokens
        # floor is a secondary safety.
        if reasoning_disabled_for_backbone(self.backbone_id):
            env["OPENROUTER_REASONING_DISABLE"] = "1"
        mt_floor = max_tokens_floor_for_backbone(self.backbone_id)
        if mt_floor:
            env["OPENROUTER_MAX_TOKENS_FLOOR"] = str(mt_floor)

        cmd = [str(AGENTCLINIC_PY), "-c", _FOLLOWUP_DRIVER]
        proc = subprocess.run(
            cmd,
            cwd=str(AGENTCLINIC_ROOT),
            env=env,
            input=json.dumps(
                {
                    "dialogue": dialogue[:8000],
                    "final_dx": final_dx or "",
                    "case_question": case_question[:6000],
                }
            ),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            return ""
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    r = json.loads(line)
                    return r.get("final", "") or ""
                except json.JSONDecodeError:
                    continue
        return ""

    # --------------------------------------------------------------

    def predict(
        self,
        case: CanonicalCase,
        pillar: Pillar,
        eval_mode: EvalMode = "gold_hpo",
        run_id: Optional[str] = None,
    ) -> PredictionLog:
        log = self._new_log(case, pillar, eval_mode, run_id)
        question = case_to_question(case, eval_mode=eval_mode)
        scenario = _build_scenario(case)

        try:
            parsed, latency_ms, stdout_full = self._run_osce(scenario)
        except subprocess.TimeoutExpired:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=self._timeout_s * 1000,
                status="timeout",
                error_message=f"agentclinic exceeded {self._timeout_s}s",
            )
        except Exception as e:  # noqa: BLE001
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=0,
                status="agent_error",
                error_message=f"{type(e).__name__}: {e}",
            )

        # Build dialogue string for the follow-up call + log
        dialogue_lines = []
        for doc, pat in zip(parsed["doctor_turns"], parsed["patient_turns"]):
            dialogue_lines.append(f"Doctor: {doc}")
            dialogue_lines.append(f"Patient: {pat}")
        # Append any trailing doctor turn without a matching patient turn
        if len(parsed["doctor_turns"]) > len(parsed["patient_turns"]):
            for doc in parsed["doctor_turns"][len(parsed["patient_turns"]):]:
                dialogue_lines.append(f"Doctor: {doc}")
        for meas in parsed["measurement_turns"]:
            dialogue_lines.append(f"Measurement: {meas}")
        dialogue = "\n".join(dialogue_lines)

        # Run follow-up call to elicit a top-5 (the Doctor only emits 1 final).
        followup_text = self._run_followup(
            dialogue, parsed.get("final_dx"), question
        )
        ranked_names = parse_ranked_top5(followup_text, k=5)

        # Always seat the Doctor's final dx at rank 1 if we have one and the
        # follow-up either failed or didn't mention it.
        if parsed.get("final_dx"):
            doc_dx = parsed["final_dx"]
            if not ranked_names:
                ranked_names = [doc_dx]
            elif doc_dx.lower() not in (n.lower() for n in ranked_names):
                ranked_names = [doc_dx] + ranked_names[:4]

        if not ranked_names:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                reasoning_trace=dialogue[:8000],
                raw_response_excerpt=followup_text or dialogue[:2000],
                latency_ms=latency_ms,
                status="parser_error",
                error_message="No diagnosis emitted by Doctor or follow-up call.",
            )

        ranked_ids, ranked_variants = map_names_to_ids_with_variants(ranked_names[:5])

        # Cost: AgentClinic doesn't return usage. Estimate from text volumes.
        prompt_tok = estimate_tokens(question) + estimate_tokens(dialogue)
        completion_tok = estimate_tokens(followup_text) + estimate_tokens(
            "\n".join(parsed["doctor_turns"])
        )
        cost = CostBreakdown(
            prompt_tokens=int(prompt_tok),
            completion_tokens=int(completion_tok),
            provider="openrouter",
        )
        log.cost = cost
        # FIX D2 (2026-05-15): compute cost_usd from backbone price table.
        fill_cost_from_tokens(log.cost, self.backbone_id)
        log.extra["agentclinic_n_inferences"] = parsed.get("n_inferences", 0)
        log.extra["agentclinic_doctor_final_dx"] = parsed.get("final_dx")
        log.extra["agentclinic_verdict"] = parsed.get("verdict")
        log.extra["agentclinic_correct_dx"] = parsed.get("correct_dx")
        log.extra["agentclinic_ranked_names"] = ranked_names
        log.extra["ranked_predictions_variants"] = ranked_variants

        return self._finalize_log(
            log,
            ranked_predictions=ranked_ids,
            reasoning_trace=dialogue[:8000],
            raw_response_excerpt=(followup_text or dialogue)[:2000],
            latency_ms=latency_ms,
            status="ok",
        )


__all__ = ["AgentClinicAdapter"]


if __name__ == "__main__":
    from harness.ingest import ingest_rarebench

    adapter = AgentClinicAdapter(
        backbone_id="openrouter/google/gemini-3-flash-preview"
    )
    case = next(
        ingest_rarebench(
            "data/rarebench_hf/data_unzipped/data/RAMEDIS.jsonl",
            "RAMEDIS",
            limit=1,
        )
    )
    print(f"[agentclinic] case_id={case.case_id} hpo_n={len(case.gold_hpo_terms)}")
    log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
    print(f"Status: {log.status}")
    print(f"Ranked predictions: {log.ranked_predictions[:5]}")
    print(f"Ranked names: {log.extra.get('agentclinic_ranked_names')}")
    print(f"Doctor final dx: {log.extra.get('agentclinic_doctor_final_dx')}")
    print(f"Verdict: {log.extra.get('agentclinic_verdict')}")
    print(f"#inferences: {log.extra.get('agentclinic_n_inferences')}")
    print(
        f"Tokens: {log.cost.prompt_tokens}+{log.cost.completion_tokens} "
        f"({log.cost.provider})"
    )
    print(f"Latency: {log.total_latency_ms}ms")
    if log.error_message:
        print(f"Error: {log.error_message}")

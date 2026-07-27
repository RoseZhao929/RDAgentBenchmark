"""MedAgents harness adapter.

MedAgents is a domain-classification + per-expert-analysis + synthesis + vote
pipeline (`syn_verif` in upstream). The upstream `run.py` is hardwired to
MCQA datasets (MedQA, etc.). For rare-disease DDx we drive the underlying
multi-agent primitive (`api_handler.get_output_multiagent` from
`api_utils.py`) directly via a small driver script that:

1. Asks N domain-expert roles (auto-recruited from the case description).
2. Each role drafts a top-5 DDx for the case.
3. A synthesiser produces a final ranked top-5.

The synthesiser's free-text top-5 is regex-parsed and mapped to ORPHA IDs.

We run the driver inside `agents/medagents/.venv/bin/python` via subprocess
(its `openai==0.27.4` SDK conflicts with newer SDKs in the harness venv).
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
import time
from pathlib import Path
from typing import Optional

from harness.agents._adapter_utils import (
    PROJECT_ROOT,
    case_to_question,
    estimate_tokens,
    fill_cost_from_tokens,
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


MEDAGENTS_ROOT = PROJECT_ROOT / "agents" / "medagents"
MEDAGENTS_PY = MEDAGENTS_ROOT / ".venv" / "bin" / "python"


# Driver snippet executed inside MedAgents' venv. Reads {"question": "..."}
# from stdin, emits one JSON object on stdout {"final": "...", "experts": {...},
# "domains": [...], "usage": {...}}.
_MEDAGENTS_DRIVER = textwrap.dedent(
    r"""
    import json, os, sys, traceback
    # api_utils.py lives at the medagents repo root; cwd is set by the caller.
    sys.path.insert(0, os.getcwd())
    try:
        from api_utils import api_handler
    except Exception as e:
        print(json.dumps({"error": "import_failed", "msg": str(e),
                          "tb": traceback.format_exc()}), flush=True)
        sys.exit(0)

    payload = json.loads(sys.stdin.read())
    question = payload["question"]

    # `chatgpt` is a placeholder; api_utils ignores `self.engine` and reads
    # the model id from $CANARY_BACKBONE_MODEL.
    handler = api_handler("chatgpt")

    usage = {"prompt_chars": 0, "completion_chars": 0, "n_calls": 0}

    def call(system, user, max_tokens):
        usage["prompt_chars"] += len(system) + len(user)
        usage["n_calls"] += 1
        try:
            out = handler.get_output_multiagent(
                system, user, max_tokens=max_tokens, temperature=0.0,
            )
        except Exception as e:
            out = "ERROR." + " " + repr(e)
        usage["completion_chars"] += len(out or "")
        return out or ""

    # --- Stage 1: recruit 3 medical expert domains for this case
    domain_prompt = (
        "Given the following rare-disease clinical case, list exactly THREE "
        "medical specialty domains (one per line) that should evaluate the case. "
        "Reply with bare specialty names, no numbering, no commentary.\n\n"
        + question
    )
    domain_text = call(
        "You are a medical case triager.",
        domain_prompt,
        max_tokens=120,
    )
    domains = []
    for line in (domain_text or "").splitlines():
        nm = line.strip().lstrip("-*0123456789.) ").strip()
        if nm and not nm.lower().startswith("here"):
            domains.append(nm)
        if len(domains) >= 3:
            break
    if not domains:
        domains = ["Medical Genetics", "Pediatric Neurology",
                   "Internal Medicine"]

    # --- Stage 2: each expert drafts a top-5 DDx
    experts = {}
    for d in domains:
        sys_role = (
            f"You are a senior {d} specialist. Use your expertise to evaluate "
            "rare disease differential diagnoses concisely."
        )
        user = (
            "Case:\n" + question + "\n\n"
            "List your top 5 ranked rare-disease differential diagnoses, "
            "most likely first, in the format:\n"
            "1. <Disease Name> — <one short rationale>\n"
            "Use canonical Orphanet / OMIM disease names."
        )
        experts[d] = call(sys_role, user, max_tokens=400)

    # --- Stage 3: synthesise across the experts into a final top-5
    expert_block = "\n\n".join(
        f"### {d}\n{experts[d]}" for d in domains
    )
    sys_synth = (
        "You are a chief medical officer synthesising rare-disease "
        "differential diagnoses across multiple specialists."
    )
    user_synth = (
        "Patient case:\n" + question + "\n\n"
        "Below are top-5 differentials from each specialist:\n\n"
        + expert_block + "\n\n"
        "Produce a single consolidated top-5 ranked rare-disease list for "
        "this patient. Format exactly:\n"
        "1. <Disease Name>\n2. <Disease Name>\n3. <Disease Name>\n"
        "4. <Disease Name>\n5. <Disease Name>\n"
        "Use canonical Orphanet / OMIM names. After the list, add a short "
        "consolidated rationale (<=4 sentences)."
    )
    final = call(sys_synth, user_synth, max_tokens=600)

    print(json.dumps({
        "final": final,
        "experts": experts,
        "domains": domains,
        "usage": usage,
    }), flush=True)
    """
).strip()


class MedAgentsAdapter(AgentAdapter):
    """MedAgents shim. Pillar 2 primary; supports P5 trace via experts dict."""

    NAME = "medagents"

    # Wrapper-level retries when the synthesiser returns empty content (see
    # predict()). 2 retries ⇒ up to 3 total subprocess attempts per case.
    _MAX_EMPTY_RETRIES = 2

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
        # api_utils.py reads $CANARY_BACKBONE_MODEL — strip openrouter/ prefix.
        if backbone_id.startswith("openrouter/"):
            self._model_id = backbone_id[len("openrouter/"):]
        else:
            self._model_id = backbone_id
        self._timeout_s = int((self.agent_extra or {}).get("timeout_s", 300))

    def supports_pillar(self, pillar: Pillar) -> bool:
        return pillar in ("P2_phenotype_ddx", "P5_reasoning_communication")

    # --------------------------------------------------------------

    def _run_medagents_subprocess(
        self, question: str
    ) -> tuple[dict, int]:
        if not MEDAGENTS_PY.exists():
            raise FileNotFoundError(
                f"MedAgents venv python missing: {MEDAGENTS_PY}"
            )
        sdk_base, api_key = resolve_llm_gateway()
        env = os.environ.copy()
        env["OPENAI_API_BASE"] = sdk_base
        env["OPENROUTER_API_KEY"] = api_key
        env["OPENAI_API_KEY"] = api_key
        env["CANARY_BACKBONE_MODEL"] = self._model_id
        env["PYTHONUNBUFFERED"] = "1"
        # 2026-05-19 — propagate reasoning_effort=minimal for GPT-5 / o-series
        # so the subprocess SDK call doesn't burn `max_tokens` on hidden CoT.
        re_effort = reasoning_effort_for_backbone(self.backbone_id)
        if re_effort:
            env["OPENROUTER_REASONING_EFFORT"] = re_effort
        # 2026-07-03 — V4-Pro's unbounded reasoning eats the synthesiser's
        # max_tokens=600 → empty output → "No ranked lines". Disable reasoning
        # (reasoning={"enabled": false}); max_tokens floor is secondary safety.
        if reasoning_disabled_for_backbone(self.backbone_id):
            env["OPENROUTER_REASONING_DISABLE"] = "1"
        mt_floor = max_tokens_floor_for_backbone(self.backbone_id)
        if mt_floor:
            env["OPENROUTER_MAX_TOKENS_FLOOR"] = str(mt_floor)

        cmd = [str(MEDAGENTS_PY), "-c", _MEDAGENTS_DRIVER]
        t0 = time.time()
        proc = subprocess.run(
            cmd,
            cwd=str(MEDAGENTS_ROOT),
            env=env,
            input=json.dumps({"question": question}),
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
        )
        latency_ms = int((time.time() - t0) * 1000)
        if proc.returncode != 0:
            stderr_tail = proc.stderr[-1500:] if proc.stderr else ""
            raise RuntimeError(
                f"medagents driver exited {proc.returncode}: {stderr_tail}"
            )
        # Find last non-empty line in stdout that parses as JSON (api_utils
        # prints chatty debug lines like "Generating response for model: ...")
        result: Optional[dict] = None
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            if line.startswith("{") and line.endswith("}"):
                try:
                    result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if result is None:
            raise RuntimeError(
                "medagents driver produced no JSON. stdout tail: "
                + proc.stdout[-1500:]
            )
        if "error" in result:
            raise RuntimeError(
                f"medagents driver error: {result['error']}: {result.get('msg')}"
            )
        return result, latency_ms

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

        # Wrapper-level transient-empty retry (2026-05-28). Some backbones
        # (observed: DeepSeek V4-Flash on RareBench/MIMIC) intermittently return
        # an HTTP-200 response whose `content` is the empty string on the
        # synthesiser call. Upstream `api_utils.get_output_multiagent` only
        # retries on exceptions, so an empty-but-successful response slips
        # through as `final=""` → parser_error. We re-invoke the whole
        # subprocess up to _MAX_EMPTY_RETRIES times when `final` is *empty*. We
        # do NOT retry when `final` is non-empty but unparseable — that is a
        # genuine format issue. This is a wrapper-only robustness retry; the
        # MedAgents algorithm/prompts are untouched (see docs/baseline_repro/).
        latency_ms = 0
        final_text = ""
        empty_attempts = 0
        for empty_attempts in range(self._MAX_EMPTY_RETRIES + 1):
            try:
                result, latency_ms = self._run_medagents_subprocess(question)
            except subprocess.TimeoutExpired:
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=self._timeout_s * 1000,
                    status="timeout",
                    error_message=f"medagents exceeded {self._timeout_s}s",
                )
            except Exception as e:  # noqa: BLE001
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=0,
                    status="agent_error",
                    error_message=f"{type(e).__name__}: {e}",
                )
            final_text = result.get("final", "") or ""
            if final_text.strip():
                break

        ranked_names = parse_ranked_top5(final_text, k=5)
        if not ranked_names:
            empty = not final_text.strip()
            return self._finalize_log(
                log,
                ranked_predictions=[],
                raw_response_excerpt=final_text,
                latency_ms=latency_ms,
                status="parser_error",
                error_message=(
                    f"Empty synthesiser output after {empty_attempts + 1} "
                    "attempts (transient backbone empty-content)."
                    if empty
                    else "No ranked '1. <Name>' lines in synthesiser output."
                ),
            )

        ranked_ids, ranked_variants = map_names_to_ids_with_variants(ranked_names)

        usage = result.get("usage", {})
        prompt_tok = estimate_tokens(question) + (
            usage.get("prompt_chars", 0) // 4
        )
        completion_tok = max(
            estimate_tokens(final_text),
            usage.get("completion_chars", 0) // 4,
        )
        cost = CostBreakdown(
            prompt_tokens=int(prompt_tok),
            completion_tokens=int(completion_tok),
            provider="openrouter",
        )
        log.cost = cost
        # FIX D2 (2026-05-15): compute cost_usd from backbone price table.
        fill_cost_from_tokens(log.cost, self.backbone_id)
        log.extra["medagents_domains"] = result.get("domains", [])
        log.extra["medagents_experts"] = list(result.get("experts", {}).keys())
        log.extra["medagents_n_calls"] = usage.get("n_calls", 0)
        log.extra["medagents_ranked_names"] = ranked_names
        log.extra["ranked_predictions_variants"] = ranked_variants

        # Reasoning trace: include per-expert top-5 lists (truncated to 8k).
        experts = result.get("experts", {})
        trace_blocks = []
        for d, text in experts.items():
            trace_blocks.append(f"### {d}\n{text}")
        reasoning_trace = "\n\n".join(trace_blocks)[:8000] or None

        return self._finalize_log(
            log,
            ranked_predictions=ranked_ids,
            reasoning_trace=reasoning_trace,
            raw_response_excerpt=final_text,
            latency_ms=latency_ms,
            status="ok",
        )


__all__ = ["MedAgentsAdapter"]


if __name__ == "__main__":
    from harness.ingest import ingest_rarebench

    adapter = MedAgentsAdapter(
        backbone_id="openrouter/google/gemini-3-flash-preview"
    )
    case = next(
        ingest_rarebench(
            "data/rarebench_hf/data_unzipped/data/RAMEDIS.jsonl",
            "RAMEDIS",
            limit=1,
        )
    )
    print(f"[medagents] case_id={case.case_id} hpo_n={len(case.gold_hpo_terms)}")
    log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
    print(f"Status: {log.status}")
    print(f"Ranked predictions: {log.ranked_predictions[:5]}")
    print(f"Ranked names: {log.extra.get('medagents_ranked_names')}")
    print(f"Domains: {log.extra.get('medagents_domains')}")
    print(
        f"Tokens: {log.cost.prompt_tokens}+{log.cost.completion_tokens} "
        f"({log.cost.provider})"
    )
    print(f"Latency: {log.total_latency_ms}ms")
    if log.error_message:
        print(f"Error: {log.error_message}")

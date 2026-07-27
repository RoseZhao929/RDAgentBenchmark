"""MAI-DxO adapter — Microsoft Diagnostic Orchestrator (community port).

Wraps `agents/maidxo/mai_dx/MaiDxOrchestrator` (patched per
`tasks/stream_E_agent_scouting/agents/maidxo_RUN_REPORT.md`) under our
`AgentAdapter` contract.

Design notes
------------
- **Subprocess** rather than in-process import. Reasons:
  1. `swarms`/`litellm` pull a heavy dependency graph that conflicts with the
     harness venv (swarms-12 needs Python 3.10–3.12, the harness runs 3.13
     and pins `pydantic` differently).
  2. The orchestrator emits ad-hoc logger output + per-call sleeps that we
     do not want to pollute the harness process with.
  3. Mirrors the smoke tests in `agents/maidxo/smoke_test*.py`.
- The subprocess runs a small in-line Python program against the maidxo venv
  (`agents/maidxo/.venv/bin/python -c <script>`), passes initial/full case
  text + ground truth on stdin (JSON), and reads the orchestrator's
  `DiagnosisResult` back as JSON on stdout.
- The orchestrator outputs a single Judge-scored final diagnosis string.
  We project that to `ranked_predictions = [final_diagnosis]`. If
  `case_state.differential_diagnosis` is non-empty (Dr. Hypothesis ran), we
  use that ranking (highest probability first) instead. The Judge's score and
  reasoning are returned in `extra` / `reasoning_trace`.
- **Pillar support**: Pillar 2 only. MAI-DxO is phenotype/text driven and
  does not consume VCF, family pedigrees, or emit HPO IDs.
- **Variants** (via `mode` ctor arg / `agent_extra`):
  - `instant` (~10 s, single Judge call, degenerate baseline)
  - `question_only`
  - `budgeted` (requires `budget_usd` in `agent_extra`)
  - `no_budget` (default — full 8-agent panel + Judge)
  - `ensemble` (single-orchestrator config, ensemble aggregation deferred)

Verification (instant mode, low cost):
    python -m harness.agents.maidxo
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.agents._adapter_utils import (
    estimate_tokens,
    fill_cost_from_tokens,
    map_names_to_ids,
    reasoning_effort_for_backbone,
    resolve_llm_gateway,
    wire_model_id,
)
from harness.agents.base import AgentAdapter
from harness.canonical_case import CanonicalCase
from harness.logging.schema import EvalMode, Pillar, PredictionLog
from harness.pmc_oa.orphanet import map_diagnosis, parse_orphadata

# Repo layout: harness/agents/maidxo.py → project root is parents[2]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MAIDXO_DIR = _PROJECT_ROOT / "agents" / "maidxo"
_MAIDXO_PYTHON = _MAIDXO_DIR / ".venv" / "bin" / "python"

_VALID_MODES = {"instant", "question_only", "budgeted", "no_budget", "ensemble"}


# FIX 2026-05-16: noise filter for ranked_predictions. A4 cross-map audit on
# 2026-05-15 found ~10/50 maidxo top-1 entries were vital signs, lab values,
# sentence fragments, or "Unable to establish ..." stubs rather than disease
# names. These poison R@1 and confuse the LLM judge. We drop any candidate
# matching one of the noise patterns below before handing the list to the
# fuzzy-ORPHA fallback / final ranking.
_NOISE_PATTERNS = [
    re.compile(r"^\s*unable to (establish|determine|identify|formulate)", re.I),
    re.compile(r"^\s*cannot\s", re.I),
    re.compile(r"^\s*further evaluation", re.I),
    re.compile(
        r"(mmHg|bpm|mg/dL|°C|SpO2|hemoglobin|creatinine\s+\d|glucose\s+\d)",
        re.I,
    ),
    re.compile(r"^\s*\d+\.\d+\s*$"),  # bare numbers
    re.compile(r"^\s*(though|however|but|note that)", re.I),  # sentence fragments
    # 2026-05-19 patch — caught in maidxo v3 / Phase 2:
    re.compile(r"^\s*failure to ", re.I),               # "Failure to achieve..."
    re.compile(r"^\s*could not ", re.I),
    re.compile(r"^\s*did not ", re.I),
    re.compile(r"^\s*no (evidence of|significant)", re.I),
    # 2026-05-19 patch — caught from DeepSeek V3.2 + maidxo audit:
    re.compile(r"\b(DLCO|LVEF|FEV1?|FVC|TLC)\b"),       # pulmonary / cardiac functions
    re.compile(r"^\s*(restrictive|obstructive) pattern", re.I),  # PFT patterns
    re.compile(r"^\s*ejection fraction", re.I),
]


def _is_noise_candidate(s: str) -> bool:
    """Return True if `s` is clearly not a disease name (vitals / fragments)."""
    if not s or len(s.strip()) < 3:
        return True
    return any(p.search(s) for p in _NOISE_PATTERNS)


def _hpo_to_vignette(case: CanonicalCase) -> str:
    """Synthesize a one-paragraph clinical vignette from a CanonicalCase.

    Uses `free_text_vignette` or `synthetic_vignette` if present, otherwise
    falls back to a deterministic listing of HPO labels (Pillar 2 baseline
    input).
    """
    if case.free_text_vignette:
        return case.free_text_vignette
    if case.synthetic_vignette:
        return case.synthetic_vignette

    demo = case.demographics
    age = demo.age_at_onset_years
    sex = demo.sex
    bits: List[str] = []
    if age is not None or sex:
        age_str = f"{age:.0f}-year-old" if age is not None else "patient of unknown age"
        sex_str = sex if sex and sex != "unknown" else ""
        bits.append(f"A {age_str} {sex_str}".strip())
    else:
        bits.append("A patient")

    present = [t for t in case.gold_hpo_terms if not t.negated]
    absent = [t for t in case.gold_hpo_terms if t.negated]

    if present:
        labels = ", ".join(t.label or t.id for t in present)
        bits.append(f"presents with: {labels}.")
    if absent:
        labels = ", ".join(t.label or t.id for t in absent)
        bits.append(f"Notably absent: {labels}.")
    return " ".join(bits)


# Inline subprocess runner — string-formatted Python program that the maidxo
# venv interpreter executes. JSON in (stdin) / JSON out (stdout).
_RUNNER_SOURCE = r"""
import json
import os
import sys
import time

# Read configuration from stdin
config = json.loads(sys.stdin.read())

os.chdir(config["maidxo_dir"])

# Honour API key for LiteLLM
if config.get("openrouter_api_key"):
    os.environ["OPENROUTER_API_KEY"] = config["openrouter_api_key"]
# Route LiteLLM's openrouter/* calls at the authorized gateway. LiteLLM reads
# OPENROUTER_API_BASE for the openrouter provider; also set OPENAI_* as a
# fallback for any openai/* routing inside swarms.
if config.get("openrouter_api_base"):
    os.environ["OPENROUTER_API_BASE"] = config["openrouter_api_base"]
    os.environ["OPENAI_API_BASE"] = config["openrouter_api_base"]
    os.environ["OPENAI_BASE_URL"] = config["openrouter_api_base"]

from mai_dx import MaiDxOrchestrator  # noqa: E402

variant_kwargs = {
    "model_name": config["model_name"],
    "max_iterations": config["max_iterations"],
    "request_delay": config["request_delay"],
}
if config.get("budget_usd") is not None:
    variant_kwargs["budget"] = float(config["budget_usd"])
# 2026-05-19 — propagate reasoning_effort=minimal for GPT-5 / o-series so
# LiteLLM doesn't hit OpenRouter with default-high reasoning that burns the
# entire max_tokens budget on hidden CoT.
if config.get("reasoning_effort"):
    variant_kwargs["reasoning_effort"] = config["reasoning_effort"]

t0 = time.time()
try:
    orch = MaiDxOrchestrator.create_variant(config["mode"], **variant_kwargs)
    result = orch.run(
        initial_case_info=config["initial_case_info"],
        full_case_details=config["full_case_details"],
        ground_truth_diagnosis=config["ground_truth_diagnosis"],
    )
    elapsed = time.time() - t0
    cs = getattr(orch, "case_state", None)
    differential = {}
    if cs is not None and getattr(cs, "differential_diagnosis", None):
        differential = dict(cs.differential_diagnosis)

    out = {
        "ok": True,
        "final_diagnosis": result.final_diagnosis,
        "ground_truth": result.ground_truth,
        "accuracy_score": result.accuracy_score,
        "accuracy_reasoning": result.accuracy_reasoning,
        "total_cost_simulated_usd": result.total_cost,
        "iterations": result.iterations,
        "conversation_history": result.conversation_history,
        "differential_diagnosis": differential,
        "elapsed_seconds": elapsed,
    }
except Exception as e:  # noqa: BLE001
    out = {
        "ok": False,
        "error": f"{type(e).__name__}: {e}",
        "elapsed_seconds": time.time() - t0,
    }

sys.stdout.write("__MAIDXO_RESULT__" + json.dumps(out))
"""


def _parse_disease_from_diagnosis(text: str) -> str:
    """Pull a clean disease name from a long, sometimes prose-y diagnosis string."""
    if not text:
        return ""
    # First non-empty line, stripped of trailing punctuation
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), text.strip())
    # Cut at common diagnostic prefixes
    for sep in [":", " - ", " — "]:
        if sep in first_line and first_line.split(sep)[0].lower() in {
            "final diagnosis",
            "diagnosis",
            "primary diagnosis",
        }:
            first_line = first_line.split(sep, 1)[1].strip()
    # Strip trailing period
    return first_line.rstrip(".").strip()


def _clean_for_fuzzy(name: str) -> str:
    """Strip parenthetical clarifiers + 'with/and/or' qualifiers so fuzzy
    matching has a cleaner head to compare against ORPHA names.

    Used by the FIX-D1 fuzzy-fallback path. Keep this conservative — we'd
    rather under-clean (and miss a match) than over-clean (and produce a
    spurious match like "syndrome" → anything).
    """
    import re as _re

    n = _re.sub(r"\s*\([^)]*\)\s*", " ", name).strip()
    low = n.lower()
    for sep in [" with ", " and ", " or ", " due to ", " featuring ", ", "]:
        idx = low.find(sep)
        if idx > 0:
            n = n[:idx].strip()
            low = n.lower()
    return n.strip()


class MaiDxOAdapter(AgentAdapter):
    """Adapter for the MAI-DxO multi-agent panel.

    Construct with `agent_extra={"mode": "no_budget", "max_iterations": 3, ...}`
    or rely on defaults below.

    Keys recognised in `agent_extra`:
    - `mode`: one of {"instant", "question_only", "budgeted", "no_budget",
      "ensemble"}. Default "no_budget".
    - `max_iterations`: int. Default 3 (no_budget) / 1 (instant).
    - `request_delay`: float seconds. Default 0.0 (harness owns throttling).
    - `budget_usd`: float (only honoured for `mode="budgeted"`).
    - `timeout_seconds`: subprocess wall-clock cap. Default 600.
    - `maidxo_python`: override path to the maidxo venv interpreter.

    Note on `max_iterations`: the source paper expects ≥ 2 to get a real
    diagnosis from `no_budget` (round 1 = test ordering, round 2 = diagnose).
    Default of 3 balances cost (~$0.03–$0.06 / case at Gemini 3 Flash) vs.
    finishing. `instant` mode short-circuits after 1 iteration by design and
    is wired here so ablation A11 has a degenerate-baseline knob.
    """

    NAME = "maidxo"

    DEFAULT_MAX_ITER = 3
    DEFAULT_TIMEOUT_S = 600

    def __init__(
        self,
        backbone_id: str = "openrouter/google/gemini-3-flash-preview",
        backbone_temperature: float = 0.0,
        backbone_seed: Optional[int] = None,
        agent_extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            backbone_id=backbone_id,
            backbone_temperature=backbone_temperature,
            backbone_seed=backbone_seed,
            agent_extra=agent_extra,
        )
        mode = self.agent_extra.get("mode", "no_budget")
        if mode not in _VALID_MODES:
            raise ValueError(
                f"Unknown MAI-DxO mode: {mode!r}. "
                f"Valid: {sorted(_VALID_MODES)}"
            )
        self.mode = mode
        # `instant` natively runs only 1 iter; users can override.
        default_iter = 1 if mode == "instant" else self.DEFAULT_MAX_ITER
        self.max_iterations = int(self.agent_extra.get("max_iterations", default_iter))
        self.request_delay = float(self.agent_extra.get("request_delay", 0.0))
        self.budget_usd = self.agent_extra.get("budget_usd")
        self.timeout_seconds = int(
            self.agent_extra.get("timeout_seconds", self.DEFAULT_TIMEOUT_S)
        )
        self._maidxo_python = Path(
            self.agent_extra.get("maidxo_python", _MAIDXO_PYTHON)
        )
        if not self._maidxo_python.exists():
            raise FileNotFoundError(
                f"MAI-DxO venv interpreter not found at {self._maidxo_python}. "
                "Run install steps in agents/maidxo/."
            )

    def supports_pillar(self, pillar: Pillar) -> bool:
        # MAI-DxO is phenotype/text-only; no VCF, no pedigree, no HPO extraction.
        # P5 (reasoning) re-uses the P2 pipeline — the panel debate is the trace.
        return pillar in ("P2_phenotype_ddx", "P5_reasoning_communication")

    # -------- main entry --------

    def predict(
        self,
        case: CanonicalCase,
        pillar: Pillar,
        eval_mode: EvalMode = "gold_hpo",
        run_id: Optional[str] = None,
    ) -> PredictionLog:
        log = self._new_log(case, pillar, eval_mode, run_id)

        if pillar not in ("P2_phenotype_ddx", "P5_reasoning_communication"):
            return self._finalize_log(
                log,
                ranked_predictions=[],
                status="skipped",
                error_message=f"MAI-DxO does not support pillar {pillar}.",
            )

        vignette = _hpo_to_vignette(case)

        # The orchestrator distinguishes between "initial case info" (shown to
        # the panel) and "full case details" (held by the Gatekeeper). For
        # Pillar 2 (phenotype-only) we give the same text to both — we have
        # nothing extra to gate on. The Judge uses gold_label.disease_name.
        ground_truth = (
            case.gold_label.disease_name
            or case.gold_label.omim_id
            or case.gold_label.orphanet_id
            or "Unknown"
        )

        # Backbone id may carry the "openrouter/" prefix already; LiteLLM
        # expects exactly that for OpenRouter routing.
        # 2026-07-27 — normalize dated OpenRouter aliases to the ids the current
        # gateway publishes (see wire_model_id); self.backbone_id stays canonical
        # for cost accounting and output filenames.
        model_name = wire_model_id(self.backbone_id)
        if not model_name.startswith(("openrouter/", "openai/", "gemini/", "anthropic/")):
            # Default to OpenRouter prefix if user passed a bare id.
            model_name = f"openrouter/{model_name}"

        # 2026-05-19 — propagate reasoning_effort=minimal for GPT-5 / o-series.
        # MAI-DxO uses swarms.Agent (LiteLLM under the hood); we wire this in
        # via env var so the in-line runner script picks it up.
        re_effort = reasoning_effort_for_backbone(self.backbone_id)

        _gw_base, _gw_key = resolve_llm_gateway()
        config = {
            "maidxo_dir": str(_MAIDXO_DIR),
            "openrouter_api_key": _gw_key or os.environ.get("OPENROUTER_API_KEY", ""),
            "openrouter_api_base": _gw_base,
            "model_name": model_name,
            "mode": self.mode,
            "max_iterations": self.max_iterations,
            "request_delay": self.request_delay,
            "budget_usd": self.budget_usd if self.mode == "budgeted" else None,
            "initial_case_info": vignette,
            "full_case_details": vignette,
            "ground_truth_diagnosis": ground_truth,
            "reasoning_effort": re_effort,
        }

        t0 = time.time()
        _subproc_env = {**os.environ}
        if re_effort:
            _subproc_env["OPENROUTER_REASONING_EFFORT"] = re_effort
        try:
            proc = subprocess.run(
                [str(self._maidxo_python), "-c", _RUNNER_SOURCE],
                input=json.dumps(config),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=_subproc_env,
            )
        except subprocess.TimeoutExpired:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=int((time.time() - t0) * 1000),
                status="timeout",
                error_message=f"MAI-DxO subprocess exceeded {self.timeout_seconds}s",
            )

        latency_ms = int((time.time() - t0) * 1000)

        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout)[-1500:]
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=latency_ms,
                status="agent_error",
                error_message=f"MAI-DxO returncode={proc.returncode}; stderr tail:\n{tail}",
            )

        # Result is delimited by sentinel so logger noise can't poison stdout.
        marker = "__MAIDXO_RESULT__"
        idx = proc.stdout.rfind(marker)
        if idx < 0:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=latency_ms,
                status="parser_error",
                error_message=(
                    "MAI-DxO subprocess produced no result sentinel. "
                    f"stdout tail: {proc.stdout[-800:]!r}"
                ),
            )
        try:
            result = json.loads(proc.stdout[idx + len(marker):].strip())
        except json.JSONDecodeError as e:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=latency_ms,
                status="parser_error",
                error_message=f"MAI-DxO JSON parse failed: {e}; raw: {proc.stdout[-800:]!r}",
            )

        if not result.get("ok"):
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=latency_ms,
                status="agent_error",
                error_message=result.get("error", "unknown MAI-DxO failure"),
            )

        # Build ranked predictions
        differential = result.get("differential_diagnosis") or {}
        ranked: List[str] = []
        confidences: List[float] = []
        if differential:
            ranked_items = sorted(
                differential.items(), key=lambda kv: kv[1], reverse=True
            )
            ranked = [k for k, _ in ranked_items]
            confidences = [float(v) for _, v in ranked_items]

        final_dx = _parse_disease_from_diagnosis(result.get("final_diagnosis", ""))
        if final_dx and final_dx not in ranked:
            ranked = [final_dx, *ranked]
            confidences = [1.0, *confidences]

        # ----- FIX 2026-05-16: noise filter -----
        # Drop vitals / sentence-fragment / "Unable to establish" candidates
        # before they reach R@1. Audit on 2026-05-15 found ~10/50 maidxo top-1
        # entries were these (see CROSSMAP_AUDIT.md). We log what was dropped
        # for traceability.
        if ranked:
            kept: List[str] = []
            kept_conf: List[float] = []
            dropped: List[str] = []
            for i, name in enumerate(ranked):
                if _is_noise_candidate(name):
                    dropped.append(name[:120])
                    continue
                kept.append(name)
                kept_conf.append(confidences[i] if i < len(confidences) else 0.0)
            if dropped:
                log.extra["maidxo_noise_filtered"] = dropped
            ranked = kept
            confidences = kept_conf

        if not ranked:
            # Everything was noise — mark explicitly so downstream metrics
            # don't credit a vital sign string as a "prediction". Use
            # `parser_error` (the closest valid status) and surface the
            # cause via error_message.
            return self._finalize_log(
                log,
                ranked_predictions=[],
                reasoning_trace=None,
                latency_ms=latency_ms,
                status="parser_error",
                error_message=(
                    "All ranked predictions filtered as noise "
                    "(vitals / fragments / 'Unable to establish ...')."
                ),
            )

        # ----- FIX D1 (2026-05-15): fuzzy-ORPHA fallback -----
        # MAI-DxO often returns a single long-form diagnosis string with no
        # ORPHA ID; cross-map then misses. Also: when `differential_diagnosis`
        # IS populated, its keys are still prose names (not ORPHA), so the
        # whole ranked list can be unmatched. We map each rank-i prose name
        # to an ORPHA via `harness.pmc_oa.orphanet.map_diagnosis` and insert
        # the ORPHA ID at rank-i (alongside the original prose). For the
        # primary final_dx specifically, the ORPHA goes to position 0 so R@1
        # has a chance.
        try:
            tables = parse_orphadata()
        except Exception as e:  # noqa: BLE001
            tables = None
            log.extra["maidxo_fuzzy_fallback_error"] = f"orphadata load: {type(e).__name__}: {e}"

        if tables is not None and ranked:
            new_ranked: List[str] = []
            new_conf: List[float] = []
            ranked_variants: List[List[str]] = []  # 2026-05-19 fuzzy-tie fix
            fuzzy_audit: List[dict] = []
            for i, name in enumerate(ranked[:5]):
                # Skip junk fragments that obviously aren't disease names.
                unhelpful = name.strip().lower().startswith(
                    ("unable to establish", "no diagnosis", "unknown", "indeterminate")
                )
                # Heuristic for junk: lots of digits, units, parens-only, < 5 chars
                if (
                    unhelpful
                    or len(name) < 5
                    or sum(c.isdigit() for c in name) > len(name) * 0.3
                    or name.lower() in {"dlco", "femg"}
                ):
                    new_ranked.append(name)
                    new_conf.append(confidences[i] if i < len(confidences) else 0.0)
                    ranked_variants.append([name])
                    continue
                cleaned = _clean_for_fuzzy(name)
                mapped = map_diagnosis(cleaned or name, tables, return_top_k=5)
                if not mapped.get("orpha_id") and cleaned != name:
                    mapped = map_diagnosis(name, tables, return_top_k=5)
                fuzzy_audit.append({
                    "rank": i + 1,
                    "input": name[:80],
                    "orpha": mapped.get("orpha_id"),
                    "type": mapped.get("match_type"),
                    "score": mapped.get("score"),
                })
                orpha = mapped.get("orpha_id")
                if orpha:
                    # ORPHA at rank-i (prose dropped — evaluator only credits IDs).
                    new_ranked.append(orpha)
                    new_conf.append(
                        confidences[i] if i < len(confidences) else
                        float(mapped.get("score", 100.0)) / 100.0
                    )
                    # 2026-05-19 fuzzy-tie variants: collect ORPHAs scoring
                    # within 5 pts of top, plus the original prose
                    cands = mapped.get("top_candidates", []) or []
                    top_sc = max((c.get("score", 0.0) for c in cands), default=0.0)
                    tied = [c["orpha_id"] for c in cands
                            if c.get("orpha_id") and c.get("score", 0.0) >= max(88.0, top_sc - 5.0)]
                    if orpha not in tied: tied.insert(0, orpha)
                    if name not in tied: tied.append(name)
                    ranked_variants.append(tied)
                else:
                    # No mapping: keep prose as-is; metrics likely miss.
                    new_ranked.append(name)
                    new_conf.append(confidences[i] if i < len(confidences) else 0.0)
                    ranked_variants.append([name])
            ranked = new_ranked
            confidences = new_conf
            if ranked_variants:
                log.extra["ranked_predictions_variants"] = ranked_variants
            if fuzzy_audit:
                log.extra["maidxo_fuzzy_fallback"] = fuzzy_audit

        # Persist judge / cost / iterations as extras
        log.extra.update(
            {
                "maidxo_mode": self.mode,
                "max_iterations": self.max_iterations,
                "iterations_used": result.get("iterations"),
                "judge_score": result.get("accuracy_score"),
                "judge_reasoning": result.get("accuracy_reasoning"),
                "simulated_cost_usd": result.get("total_cost_simulated_usd"),
            }
        )
        # FIX D2 (2026-05-15): MAI-DxO doesn't surface LiteLLM token totals.
        # Estimate prompt+completion from the conversation_history string and
        # the final diagnosis, then convert to USD via the price table.
        # conversation_history is a single string (Conversation.get_str()), so
        # iterating it would yield characters — count length directly.
        conv_text = result.get("conversation_history") or ""
        if isinstance(conv_text, list):
            # Defensive — older versions sometimes returned a list of dicts.
            parts: List[str] = []
            for turn in conv_text:
                if isinstance(turn, dict):
                    parts.append(str(turn.get("content") or turn.get("text") or ""))
                else:
                    parts.append(str(turn))
            conv_text = "\n".join(parts)
        conv_chars = len(conv_text)
        completion_chars = 0
        for txt in (result.get("final_diagnosis", ""), result.get("accuracy_reasoning") or ""):
            completion_chars += len(txt or "")
        log.cost.prompt_tokens = max(log.cost.prompt_tokens, conv_chars // 4)
        log.cost.completion_tokens = max(
            log.cost.completion_tokens, completion_chars // 4
        )
        log.cost.provider = "openrouter"
        fill_cost_from_tokens(log.cost, self.backbone_id)

        # FIX P5-1 (2026-05-15): build a richer reasoning_trace for the LLM
        # judge — the panel's conversation_history (Hypothesis / Test-Chooser /
        # Challenger / Stewardship / Checklist + Gatekeeper exchanges) plus the
        # final diagnosis and Judge's accuracy_reasoning. Previously we only
        # surfaced `accuracy_reasoning`, which is the Judge's verdict (often
        # empty / very short), giving the LLM judge nothing to grade.
        reasoning_chunks: List[str] = []
        if conv_text:
            reasoning_chunks.append("=== MAI-DxO Panel Debate ===\n" + conv_text)
        if result.get("differential_diagnosis"):
            diff_lines = [
                f"  - {name}: {prob}"
                for name, prob in sorted(
                    result["differential_diagnosis"].items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )
            ]
            reasoning_chunks.append(
                "=== Dr. Hypothesis differential ===\n" + "\n".join(diff_lines)
            )
        if result.get("final_diagnosis"):
            reasoning_chunks.append(
                "=== Final Diagnosis ===\n" + str(result["final_diagnosis"])
            )
        if result.get("accuracy_reasoning"):
            reasoning_chunks.append(
                "=== Judge Reasoning ===\n" + str(result["accuracy_reasoning"])
            )
        reasoning_trace = "\n\n".join(reasoning_chunks) if reasoning_chunks else None

        return self._finalize_log(
            log,
            ranked_predictions=ranked or [result.get("final_diagnosis", "")],
            confidence_scores=confidences or None,
            reasoning_trace=reasoning_trace,
            raw_response_excerpt=result.get("final_diagnosis", "")[:2000],
            latency_ms=latency_ms,
            status="ok",
        )


__all__ = ["MaiDxOAdapter"]


# -------- verification ----------

if __name__ == "__main__":
    # Load .env (OPENROUTER_API_KEY)
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set; aborting verify run.", file=sys.stderr)
        sys.exit(1)

    # Ensure the project root is importable.
    sys.path.insert(0, str(_PROJECT_ROOT))
    from harness.ingest import ingest_phenopacket_store  # noqa: E402

    case = next(
        ingest_phenopacket_store(_PROJECT_ROOT / "data" / "phenopacket_store" / "notebooks", limit=1)
    )
    # Use `instant` mode for verify — ~10 s wall clock, validates wiring.
    # For real benchmark use `mode="no_budget"` with max_iterations >= 2.
    adapter = MaiDxOAdapter(
        backbone_id="openrouter/google/gemini-3-flash-preview",
        agent_extra={"mode": "instant", "max_iterations": 1, "request_delay": 0.0},
    )
    log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
    print("=== MaiDxOAdapter verify ===")
    print("case_id:", log.case_id, "split:", log.source_split)
    print("status:", log.status, "error:", log.error_message)
    print("ranked_predictions[:5]:", log.ranked_predictions[:5])
    print("confidences[:5]:", log.confidence_scores[:5])
    print("latency_ms:", log.total_latency_ms)
    print("cost:", log.cost.model_dump())
    print("extra:", log.extra)

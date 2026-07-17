"""VC-RDAgent adapter — offline classical ranker (default) + optional LLM refine.

The agent has two stages:

  Stage 1 (`ensemble_disease_ranking.py`):
    Pure offline IC + Poincaré + frequency-LR ensemble (no LLM).
    This is our default mode (cheap, reproducible, LLM-bias-free).

  Stage 2 (`phenotype_to_disease_prediction_bysteps.py`):
    Optional LLM evaluator (local Qwen3-8B / OpenRouter) on top of Stage 1.
    Enabled via `use_llm_refine=True` in `agent_extra` — NOT WIRED YET in this
    shim (Stage 1 alone is what was smoke-tested; Stage 2 hook is a stub).

Pillar coverage: P2_phenotype_ddx only.

Calling convention:
  - Project the `CanonicalCase` into VC-RDAgent's `[[hpo_ids], [disease_ids]]`
    record format (a JSON file with a single sample).
  - Subprocess `agents/vc_rdagent/.venv/bin/python ensemble_disease_ranking.py`
    with `--no_prompt`.
  - Read back `samples[0].final_rankings[].disease_id` for the ranked list.

Stage 1 has cost_usd=0 by construction (no LLM call). Latency is the metric.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.agents.base import AgentAdapter
from harness.canonical_case import CanonicalCase, HpoTerm
from harness.logging.schema import EvalMode, Pillar, PredictionLog


VC_RDAGENT_ROOT = Path(
    "/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/vc_rdagent"
)
VC_RDAGENT_PYTHON = VC_RDAGENT_ROOT / ".venv" / "bin" / "python"
VC_RDAGENT_SCRIPT_DIR = VC_RDAGENT_ROOT / "pho2disease"
VC_RDAGENT_STAGE1_SCRIPT = VC_RDAGENT_SCRIPT_DIR / "ensemble_disease_ranking.py"
VC_RDAGENT_CONFIG = VC_RDAGENT_SCRIPT_DIR / "prompt_config.json"


def _flatten_disease_id(raw: Any) -> List[str]:
    """`disease_id` in VC-RDAgent output can be a string or list-of-strings.

    Return all candidate IDs (caller picks the best). Empty/None -> [].
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    return [str(raw)]


def _pick_primary_id(candidates: List[str]) -> Optional[str]:
    """From a list of candidate disease IDs, pick a canonical one.

    Priority: OMIM:* > ORPHA:* > anything else. Returns None if list empty.
    """
    omim = next((c for c in candidates if c.startswith("OMIM:")), None)
    if omim:
        return omim
    orpha = next((c for c in candidates if c.startswith("ORPHA:")), None)
    if orpha:
        return orpha
    return candidates[0] if candidates else None


class VCRDAgentAdapter(AgentAdapter):
    """Adapter for VC-RDAgent's offline Stage 1 ranker (default).

    Args:
        backbone_id: For Stage 1 this is a no-op marker (e.g., "offline/none").
                     The adapter never makes an LLM call in Stage 1.
        agent_extra: Optional dict. Recognized keys:
            - "use_llm_refine" (bool, default False): if True, route to Stage 2
              (NOT implemented in this shim — raises NotImplementedError).
            - "final_top_k" (int, default 50): how many to return in
              ranked_predictions.
            - "timeout_sec" (int, default 600): subprocess timeout.
    """

    NAME = "vc_rdagent"

    def __init__(
        self,
        backbone_id: str = "offline/none",
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
        self.use_llm_refine: bool = bool(self.agent_extra.get("use_llm_refine", False))
        self.final_top_k: int = int(self.agent_extra.get("final_top_k", 50))
        self.timeout_sec: int = int(self.agent_extra.get("timeout_sec", 600))
        # FIX D3 (2026-05-15): RareArena cases have free-text vignettes only.
        # When eval_mode="end_to_end", upstream-LLM extract HPO + normalize
        # phrase→HP-ID before invoking Stage 1.
        self.hpo_extractor_backbone: str = self.agent_extra.get(
            "hpo_extractor_backbone", "openrouter/google/gemini-3-flash-preview"
        )
        self._hpo_extractor = None  # lazy

        if not VC_RDAGENT_PYTHON.exists():
            raise RuntimeError(
                f"VC-RDAgent venv python not found at {VC_RDAGENT_PYTHON}. "
                "Run `python3 -m venv .venv && pip install -r requirements.txt` "
                f"inside {VC_RDAGENT_ROOT}."
            )
        if not VC_RDAGENT_STAGE1_SCRIPT.exists():
            raise RuntimeError(
                f"VC-RDAgent Stage 1 script not found at {VC_RDAGENT_STAGE1_SCRIPT}."
            )

    def supports_pillar(self, pillar: Pillar) -> bool:
        return pillar == "P2_phenotype_ddx"

    # ---------- core ----------

    def _get_hpo_extractor(self):
        """Lazily build an LLMControlAdapter for free-text → HPO extraction."""
        if self._hpo_extractor is not None:
            return self._hpo_extractor
        from harness.agents.llm_control import LLMControlAdapter

        self._hpo_extractor = LLMControlAdapter(
            backbone_id=self.hpo_extractor_backbone,
            backbone_temperature=0.0,
        )
        return self._hpo_extractor

    def _extract_hpo_for_end_to_end(
        self, case: CanonicalCase
    ) -> tuple[List[HpoTerm], dict]:
        """LLM Pillar-1 + phrase→HP-ID normalization. Returns (terms, debug)."""
        from harness.metrics.hpo_phrase_to_id import phrase_to_hp_id

        try:
            phrase_terms = self._get_hpo_extractor().extract_phenotypes(case)
        except Exception as e:  # noqa: BLE001
            return [], {"hpo_extraction_error": f"{type(e).__name__}: {e}"}
        phrases = [t.label for t in phrase_terms if t.label]
        resolved: List[HpoTerm] = []
        misses: List[str] = []
        seen_ids: set[str] = set()
        for ph in phrases:
            hp_id = phrase_to_hp_id(ph)
            if hp_id is None:
                misses.append(ph)
                continue
            if hp_id in seen_ids:
                continue
            seen_ids.add(hp_id)
            resolved.append(HpoTerm(id=hp_id, label=ph))
        debug = {
            "hpo_extraction_phrases_total": len(phrases),
            "hpo_extraction_phrases_resolved": len(resolved),
            "hpo_extraction_misses_sample": misses[:5],
        }
        return resolved, debug

    def _case_to_input_record(self, case: CanonicalCase) -> List[List[str]]:
        """Project CanonicalCase -> VC-RDAgent input format.

        VC-RDAgent expects `[[hpo_ids], [disease_ids]]` per sample. We don't
        leak the gold disease to the ranker — but the script's main loop
        skips samples with empty `diseases`, so we feed a single sentinel ID
        ("OMIM:000000") which is not in any annotation and therefore has no
        effect on the ranking; it only keeps the iteration alive. The gold
        diseases are stripped from the returned prediction list downstream.
        """
        hpo_ids = [t.id for t in case.gold_hpo_terms if not t.negated]
        if not hpo_ids:
            raise ValueError(
                f"case {case.case_id} has no usable gold_hpo_terms; "
                "VC-RDAgent Stage 1 requires structured HPO input."
            )
        # Sentinel disease ID — not present in any annotation file, used purely
        # to keep VC-RDAgent's per-sample loop alive (it skips empty disease
        # lists). The ranker still ranks against the full ontology.
        sentinel_disease = "OMIM:000000"
        return [hpo_ids, [sentinel_disease]]

    def _run_stage1(self, input_path: Path, output_path: Path) -> None:
        """Invoke VC-RDAgent Stage 1 ranker as subprocess."""
        cmd = [
            str(VC_RDAGENT_PYTHON),
            str(VC_RDAGENT_STAGE1_SCRIPT),
            "--config", str(VC_RDAGENT_CONFIG),
            "--input_file", str(input_path),
            "--prompt_steps", "2",
            "--no_prompt",
            "--num_samples", "1",
            "--final_top_k", str(self.final_top_k),
            "--output_file", str(output_path),
        ]
        env = os.environ.copy()
        # VC-RDAgent's ensemble_disease_ranking imports generate_prompts_bysteps
        # by relative name — must run with CWD inside its script dir.
        result = subprocess.run(
            cmd,
            cwd=str(VC_RDAGENT_SCRIPT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"VC-RDAgent Stage 1 failed (rc={result.returncode}).\n"
                f"stderr (last 2000 chars):\n{result.stderr[-2000:]}"
            )

    def _parse_output(self, output_path: Path) -> List[Dict[str, Any]]:
        """Extract `samples[0].final_rankings` from VC-RDAgent output."""
        with output_path.open() as f:
            payload = json.load(f)
        samples = payload.get("samples", [])
        if not samples:
            return []
        first = samples[0]
        # In --no_prompt mode the result is the raw process_sample dict, which
        # has `final_rankings` at the top level.
        if "final_rankings" in first:
            return first["final_rankings"]
        # In prompt mode it's nested under ensemble_info.
        if "ensemble_info" in first:
            return first["ensemble_info"].get("final_rankings", [])
        return []

    def predict(
        self,
        case: CanonicalCase,
        pillar: Pillar,
        eval_mode: EvalMode = "gold_hpo",
        run_id: Optional[str] = None,
    ) -> PredictionLog:
        log = self._new_log(case, pillar, eval_mode, run_id)

        if not self.supports_pillar(pillar):
            return self._finalize_log(
                log,
                ranked_predictions=[],
                status="skipped",
                error_message=f"VC-RDAgent does not support pillar {pillar}",
            )

        if self.use_llm_refine:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                status="skipped",
                error_message="Stage 2 (LLM refine) not wired in this shim",
            )

        # FIX D3 (2026-05-15): end_to_end + empty gold HPO → upstream-extract.
        case_for_vc = case
        used_e2e_extraction = False
        if (
            eval_mode == "end_to_end"
            and not case.gold_hpo_terms
            and (case.free_text_vignette or case.synthetic_vignette)
        ):
            extracted, debug = self._extract_hpo_for_end_to_end(case)
            log.extra.update(debug)
            used_e2e_extraction = True
            if not extracted:
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=0,
                    status="skipped",
                    error_message=(
                        "end_to_end HPO extraction yielded no usable terms"
                    ),
                )
            case_for_vc = case.model_copy(update={"gold_hpo_terms": extracted})
            log.extracted_hpo_terms = [t.id for t in extracted]

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="vcrd_") as tmp:
            tmp_dir = Path(tmp)
            input_path = tmp_dir / "input.json"
            output_path = tmp_dir / "ranking.json"

            try:
                record = self._case_to_input_record(case_for_vc)
            except Exception as e:
                latency_ms = int((time.monotonic() - t0) * 1000)
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="agent_error",
                    error_message=f"input projection: {type(e).__name__}: {e}",
                )

            input_path.write_text(json.dumps([record]))

            try:
                self._run_stage1(input_path, output_path)
            except subprocess.TimeoutExpired:
                latency_ms = int((time.monotonic() - t0) * 1000)
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="timeout",
                    error_message=f"Stage 1 timed out after {self.timeout_sec}s",
                )
            except Exception as e:
                latency_ms = int((time.monotonic() - t0) * 1000)
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="agent_error",
                    error_message=f"Stage 1 subprocess: {type(e).__name__}: {e}",
                )

            if not output_path.exists():
                latency_ms = int((time.monotonic() - t0) * 1000)
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="agent_error",
                    error_message="Stage 1 produced no output file",
                )

            try:
                final_rankings = self._parse_output(output_path)
            except Exception as e:
                latency_ms = int((time.monotonic() - t0) * 1000)
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="parser_error",
                    error_message=f"output parse: {type(e).__name__}: {e}",
                )

        latency_ms = int((time.monotonic() - t0) * 1000)

        ranked_predictions: List[str] = []
        confidence_scores: List[float] = []
        for entry in final_rankings[: self.final_top_k]:
            cands = _flatten_disease_id(entry.get("disease_id"))
            primary = _pick_primary_id(cands) or entry.get("disease_name")
            if primary is None:
                continue
            ranked_predictions.append(str(primary))
            try:
                # z-statistic: lower = better. Flip sign so higher conf = better.
                z = float(entry.get("z_statistic"))
                confidence_scores.append(-z)
            except (TypeError, ValueError):
                confidence_scores.append(0.0)

        # cost stays at zero — Stage 1 is offline by construction.
        return self._finalize_log(
            log,
            ranked_predictions=ranked_predictions,
            confidence_scores=confidence_scores,
            latency_ms=latency_ms,
            status="ok",
        )


__all__ = ["VCRDAgentAdapter"]

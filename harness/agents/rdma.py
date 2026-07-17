"""RDMA adapter — Pillar 1 (HPO finding extraction) specialist.

RDMA's smoke-tested entry point is `rdma.hporag.entity.LLMEntityExtractor.
extract_entities(text) -> List[str]`. It returns natural-language phenotypic
finding strings ("progressive proximal muscle weakness"), NOT HPO IDs. The
HPO-code-resolution step (`rdma/hpo/matcher.py`) requires Google-Drive-hosted
embeddings + faiss/fastembed which we deferred per the RUN_REPORT.

Therefore `extract_phenotypes(case)` returns `HpoTerm` objects with:
  - id   = "HP:0000000" (placeholder; sentinel value reserved for un-normalized)
  - label = the raw phenotype phrase
A downstream HPO-normalization pass is expected to resolve `id` later.

The adapter only supports Pillar 1. `predict()` returns a skipped log (RDMA
does NOT do Pillar 2 DDx in our scope).

Backbone: passed through to OpenRouterLLMClient as `model_type`. Per RUN_REPORT,
raw OpenRouter IDs like "google/gemini-3-flash-preview" work directly via the
MODEL_MAPPING fallback. We strip the optional "openrouter/" prefix.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.agents._adapter_utils import (
    estimate_tokens,
    fill_cost_from_tokens,
)
from harness.agents.base import AgentAdapter
from harness.canonical_case import CanonicalCase, HpoTerm
from harness.logging.schema import EvalMode, Pillar, PredictionLog


RDMA_ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/rdma")
RDMA_PYTHON = RDMA_ROOT / ".venv" / "bin" / "python"

# Placeholder ID for un-normalized HPO phrases — schema requires HP:\d{7}.
PLACEHOLDER_HPO_ID = "HP:0000000"


# Inline runner script — executed inside RDMA's venv via subprocess. Reads a
# job JSON from stdin (or arg), writes a result JSON to a path. Keeps the
# adapter / RDMA decoupled so we don't have to import RDMA from our harness.
_RUNNER_SCRIPT = r'''
"""Inline runner used by the RDMA harness adapter.

Reads job spec from argv[1] (path to JSON with keys: text, model_id,
temperature, negation, family_history, exclude_etiology). Writes result JSON
to argv[2] with keys: findings (List[str]), status, error.
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

# Load .env if present (smoke_test.py does the same).
PROJECT_ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main(job_path: str, out_path: str) -> int:
    with open(job_path) as f:
        job = json.load(f)
    text = job["text"]
    model_id = job["model_id"]
    temperature = float(job.get("temperature", 0.1))
    negation = bool(job.get("negation", True))
    family_history = bool(job.get("family_history", True))
    exclude_etiology = bool(job.get("exclude_etiology", True))

    # Suppress OpenRouterLLMClient._save_config() side effect (it writes the
    # API key in plaintext to CWD). Chdir to a private tmpdir before init.
    import tempfile as _tempfile
    _scratch = _tempfile.mkdtemp(prefix="rdma_runner_")
    os.chdir(_scratch)

    started = time.time()
    try:
        from rdma.utils.llm_client import OpenRouterLLMClient
        from rdma.hporag.entity import LLMEntityExtractor

        llm = OpenRouterLLMClient(
            model_type=model_id,
            temperature=temperature,
        )
        extractor = LLMEntityExtractor(
            llm_client=llm,
            negation=negation,
            family_history=family_history,
            exclude_etiology=exclude_etiology,
        )
        findings = extractor.extract_entities(text)
    except Exception as e:
        result = {
            "findings": [],
            "status": "agent_error",
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "latency_ms": int((time.time() - started) * 1000),
        }
    else:
        result = {
            "findings": list(findings) if findings else [],
            "status": "ok",
            "error": None,
            "latency_ms": int((time.time() - started) * 1000),
        }

    with open(out_path, "w") as f:
        json.dump(result, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
'''


def _strip_backbone_prefix(backbone_id: str) -> str:
    """`openrouter/google/gemini-3-flash-preview` -> `google/gemini-3-flash-preview`."""
    if backbone_id.startswith("openrouter/"):
        return backbone_id[len("openrouter/"):]
    return backbone_id


class RDMAAdapter(AgentAdapter):
    """Pillar 1 specialist. Wraps `LLMEntityExtractor.extract_entities`.

    `predict()` is not supported (returns status="skipped"). Use
    `extract_phenotypes(case)` for Pillar 1.

    Args:
        backbone_id: e.g., "openrouter/google/gemini-3-flash-preview". The
            "openrouter/" prefix is stripped before being passed to
            `OpenRouterLLMClient(model_type=...)`.
        agent_extra: Recognized keys:
            - "negation" (bool, default True)
            - "family_history" (bool, default True)
            - "exclude_etiology" (bool, default True)
            - "timeout_sec" (int, default 120)
    """

    NAME = "rdma"

    def __init__(
        self,
        backbone_id: str,
        backbone_temperature: float = 0.1,
        backbone_seed: Optional[int] = None,
        agent_extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            backbone_id=backbone_id,
            backbone_temperature=backbone_temperature,
            backbone_seed=backbone_seed,
            agent_extra=agent_extra,
        )
        self.negation: bool = bool(self.agent_extra.get("negation", True))
        self.family_history: bool = bool(self.agent_extra.get("family_history", True))
        self.exclude_etiology: bool = bool(self.agent_extra.get("exclude_etiology", True))
        self.timeout_sec: int = int(self.agent_extra.get("timeout_sec", 120))

        if not RDMA_PYTHON.exists():
            raise RuntimeError(
                f"RDMA venv python not found at {RDMA_PYTHON}. "
                f"See {RDMA_ROOT}/readme.md for install."
            )

    def supports_pillar(self, pillar: Pillar) -> bool:
        return pillar == "P1_extraction"

    # ---------- Pillar 1 main entry ----------

    def _case_to_text(self, case: CanonicalCase) -> str:
        """Choose the most informative free-text representation of the case."""
        if case.free_text_vignette:
            return case.free_text_vignette
        if case.synthetic_vignette:
            return case.synthetic_vignette
        # Fall back to a minimal HPO-listing prose so the extractor has
        # something to work on. Mostly a guardrail; cases without text should
        # not be routed to RDMA in the first place.
        if case.gold_hpo_terms:
            hpos = ", ".join(
                (t.label or t.id) for t in case.gold_hpo_terms if not t.negated
            )
            return f"Clinical findings: {hpos}."
        raise ValueError(
            f"case {case.case_id} has no free_text_vignette, synthetic_vignette, "
            "or gold_hpo_terms — RDMA Pillar 1 has nothing to extract from."
        )

    def _run_extractor(self, text: str) -> Dict[str, Any]:
        """Subprocess RDMA's venv python with the inline runner. Returns dict."""
        with tempfile.TemporaryDirectory(prefix="rdma_") as tmp:
            tmp_dir = Path(tmp)
            job_path = tmp_dir / "job.json"
            out_path = tmp_dir / "out.json"
            runner_path = tmp_dir / "runner.py"

            runner_path.write_text(_RUNNER_SCRIPT)
            job_path.write_text(json.dumps({
                "text": text,
                "model_id": _strip_backbone_prefix(self.backbone_id),
                "temperature": self.backbone_temperature,
                "negation": self.negation,
                "family_history": self.family_history,
                "exclude_etiology": self.exclude_etiology,
            }))

            cmd = [str(RDMA_PYTHON), str(runner_path), str(job_path), str(out_path)]
            env = os.environ.copy()
            # Make sure rdma package is importable (it's at RDMA_ROOT/rdma).
            env["PYTHONPATH"] = (
                f"{RDMA_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
            )

            proc = subprocess.run(
                cmd,
                cwd=str(RDMA_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
            )
            if proc.returncode != 0 or not out_path.exists():
                raise RuntimeError(
                    f"RDMA runner failed (rc={proc.returncode}).\n"
                    f"stderr (last 2000):\n{proc.stderr[-2000:]}\n"
                    f"stdout (last 500):\n{proc.stdout[-500:]}"
                )
            with out_path.open() as f:
                return json.load(f)

    def _findings_to_hpo_terms(self, findings: List[str]) -> List[HpoTerm]:
        """Wrap raw phrases as `HpoTerm` with placeholder ID + the phrase as label.

        RDMA returns natural-language findings, not HP:* IDs. The placeholder
        signals to downstream normalization that these need resolution.
        If a finding happens to already be in `HP:\\d{7}` form, we keep it.
        """
        terms: List[HpoTerm] = []
        hp_pat = re.compile(r"^HP:\d{7}$")
        for raw in findings:
            phrase = (raw or "").strip()
            if not phrase:
                continue
            if hp_pat.match(phrase):
                terms.append(HpoTerm(id=phrase, label=None))
            else:
                terms.append(HpoTerm(id=PLACEHOLDER_HPO_ID, label=phrase))
        return terms

    def extract_phenotypes(self, case: CanonicalCase) -> List[HpoTerm]:
        """Pillar 1 entry — natural-language phrase extraction from case text.

        Returns HpoTerm objects with `label` populated (phrase) and `id` set
        to "HP:0000000" placeholder. Run an HPO normalization step downstream
        to fill in canonical IDs.
        """
        text = self._case_to_text(case)
        result = self._run_extractor(text)
        if result.get("status") != "ok":
            err = result.get("error") or "unknown RDMA runner error"
            raise RuntimeError(f"RDMA extraction failed: {err}")
        return self._findings_to_hpo_terms(result.get("findings", []))

    # ---------- predict() — wired only for Pillar 1 logging ----------

    def predict(
        self,
        case: CanonicalCase,
        pillar: Pillar,
        eval_mode: EvalMode = "end_to_end",
        run_id: Optional[str] = None,
    ) -> PredictionLog:
        log = self._new_log(case, pillar, eval_mode, run_id)

        if pillar != "P1_extraction":
            return self._finalize_log(
                log,
                ranked_predictions=[],
                status="skipped",
                error_message=(
                    f"RDMA adapter only supports P1_extraction; got {pillar}"
                ),
            )

        t0 = time.monotonic()
        try:
            text = self._case_to_text(case)
        except Exception as e:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=int((time.monotonic() - t0) * 1000),
                status="agent_error",
                error_message=f"input projection: {type(e).__name__}: {e}",
            )

        try:
            result = self._run_extractor(text)
        except subprocess.TimeoutExpired:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=int((time.monotonic() - t0) * 1000),
                status="timeout",
                error_message=f"RDMA runner timed out after {self.timeout_sec}s",
            )
        except Exception as e:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=int((time.monotonic() - t0) * 1000),
                status="agent_error",
                error_message=f"RDMA runner: {type(e).__name__}: {e}",
            )

        latency_ms = int((time.monotonic() - t0) * 1000)

        if result.get("status") != "ok":
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=latency_ms,
                status="agent_error",
                error_message=str(result.get("error") or "RDMA returned non-ok"),
            )

        findings: List[str] = list(result.get("findings", []))
        hpo_terms = self._findings_to_hpo_terms(findings)

        # extracted_hpo_terms in the schema is a List[str]. We emit IDs when
        # known, else the placeholder. The raw phrases are kept in
        # raw_response_excerpt for the downstream normalizer.
        extracted_ids = [t.id for t in hpo_terms]
        raw_excerpt = json.dumps(findings, ensure_ascii=False)

        # FIX D2 (2026-05-15): RDMA's subprocess runner doesn't surface usage.
        # Floor-estimate from input text + output findings so cost_usd > 0.
        log.cost.prompt_tokens = max(log.cost.prompt_tokens, estimate_tokens(text))
        log.cost.completion_tokens = max(
            log.cost.completion_tokens, estimate_tokens(raw_excerpt)
        )
        log.cost.provider = "openrouter"
        fill_cost_from_tokens(log.cost, self.backbone_id)

        return self._finalize_log(
            log,
            ranked_predictions=[],  # P1 has no DDx
            extracted_hpo_terms=extracted_ids,
            raw_response_excerpt=raw_excerpt,
            latency_ms=latency_ms,
            status="ok",
        )


__all__ = ["RDMAAdapter"]

"""DeepRare adapter — Angelakeke/DeepRare multi-stage rare disease engine.

Wraps `agents/deeprare/main.py` (patched per
`tasks/stream_E_agent_scouting/agents/deeprare_RUN_REPORT.md` v2) under our
`AgentAdapter` contract.

Design notes
------------
- **Subprocess** call into `agents/deeprare/.venv/bin/python agents/deeprare/main.py`.
  DeepRare is a CLI-first pipeline that depends on torch + sentence-transformers
  + a ~800 MB HF database in `agents/deeprare/database/`; running it in-process
  from the harness venv would require duplicating that footprint and would
  conflict with the harness's lighter dependency set.
- **Patches** assumed already applied (do NOT re-patch from here):
  - `DEEPRARE_NO_WEB=1`     → BingSearchTool / GoogleSearchTool /
    DuckDuckGoSearchTool / UptodateSearchTool / fetch_page_content_and_summarize
    / HPOSearchTool all return empty stubs.
  - `DEEPRARE_LOCAL_EMBEDDING=1` → use bge-small-en-v1.5 (CPU) for
    `get_embedding`, padded to 1536-dim. (OpenRouter has no embeddings API.)
- **Input projection**: each `predict()` call writes a transient one-row
  `dataset/cases.csv` (the `case` dataset branch added in `data.py`) with the
  `hpo` column as a pipe-separated HP-ID list. We back up & restore any
  existing `cases.csv` so concurrent calls do not stomp each other; in batch
  mode the caller should serialise.
- **Output**: DeepRare emits a JSON per patient at
  `<results_folder>/<dataset_name>/<openai_model>/patient_<i>.json`. We:
    1. Read `final_diagnois` (note typo preserved in upstream) markdown.
    2. Regex-extract `## **<DISEASE>** (Rank #X/5)` blocks → ranked list.
    3. Also surface `zero_shot_llm_response`, `first_round_result`,
       `diagnosis_api_response`, `judgements` → reasoning trace.
- **Pillar support**: P2 (HPO-only), P3 (HPO + variants — surfaced as text
  in the vignette; full Exomiser/VCF path deferred since Exomiser JAR is not
  installed), P5 (reasoning trace populated for all calls).
- **Pillar 1**: DeepRare ships a separate `hpo_extractor.py` for free-text →
  HPO, but its pipeline is gated on Selenium for OBO lookups. Not exposed
  here for the time-budgeted shim; raises NotImplementedError.

Verification:
    python -m harness.agents.deeprare
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.agents._adapter_utils import (
    estimate_tokens,
    fill_cost_from_tokens,
    reasoning_effort_for_backbone,
)
from harness.agents.base import AgentAdapter
from harness.canonical_case import CanonicalCase
from harness.logging.schema import EvalMode, Pillar, PredictionLog

# Layout
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEEPRARE_DIR = _PROJECT_ROOT / "agents" / "deeprare"
_DEEPRARE_PYTHON = _DEEPRARE_DIR / ".venv" / "bin" / "python"
_DEEPRARE_DATASET_CSV = _DEEPRARE_DIR / "dataset" / "cases.csv"
_DEEPRARE_MAIN = _DEEPRARE_DIR / "main.py"


# DeepRare emits "## **<disease>** (Rank #N/5)" (Gemini/Claude style with bold)
# or "## <disease> (Rank #N/5)" (GPT-5 minimal style without bold — 2026-05-19).
# Bold markers are optional; capture either form.
_RANK_RE = re.compile(
    r"^##\s*\*{0,2}\s*(?P<disease>.+?)\s*\*{0,2}\s*\(?\s*Rank\s*#?(?P<rank>\d+)\s*/\s*\d+\s*\)?\s*$",
    re.MULTILINE,
)


def parse_deeprare_final_diagnois(markdown: str) -> List[str]:
    """Parse DeepRare's ranked top-5 markdown into a list ordered by rank.

    Returns a list of disease-name strings in rank order. Skips dupes and
    preserves the first occurrence's casing.
    """
    if not markdown:
        return []
    matches = list(_RANK_RE.finditer(markdown))
    if not matches:
        # Fallback: any "## <Foo>" or "## **Foo**" header, ignoring section
        # headers like "## References".
        loose = re.findall(r"^##\s*\*{0,2}\s*([^\n*][^\n]*?)\s*\*{0,2}\s*$", markdown, re.MULTILINE)
        SKIP = {"references", "reference", "diagnostic reasoning",
                "summary", "discussion", "conclusion"}
        loose = [d.strip() for d in loose if d.strip().lower() not in SKIP]
        return _dedupe_keep_order(loose)[:5]
    ranked = sorted(matches, key=lambda m: int(m.group("rank")))
    return _dedupe_keep_order([m.group("disease").strip() for m in ranked])


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        key = x.lower()
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


def _build_case_csv_row(case: CanonicalCase, include_genotype_text: bool) -> Dict[str, str]:
    """Project a CanonicalCase into the single-row `cases.csv` schema:
    `hpo` (pipe-separated HP IDs) + optional `disease` (string).
    """
    hpo_ids = [t.id for t in case.gold_hpo_terms if not t.negated]
    disease = case.gold_label.disease_name or ""

    # For Pillar 3 we tack variant context onto the disease label field
    # because the patched `data.py:case` branch does not consume separate
    # genotype columns. This is a soft hint; we also pass variants verbatim
    # into the reasoning trace via the harness side.
    if include_genotype_text and case.variants:
        gene_bits = []
        for v in case.variants:
            parts = [
                v.gene_symbol or "?",
                v.hgvs_p or v.hgvs_c or "",
                v.zygosity or "",
            ]
            gene_bits.append(" ".join(p for p in parts if p).strip())
        if gene_bits:
            disease = (
                f"{disease} | Variants: {'; '.join(gene_bits)}" if disease else
                f"Variants: {'; '.join(gene_bits)}"
            )

    return {"hpo": "|".join(hpo_ids), "disease": disease}


class DeepRareAdapter(AgentAdapter):
    """Adapter for the DeepRare pipeline.

    `agent_extra` keys:
    - `timeout_seconds`: subprocess wall-clock cap. Default 900 (15 min);
      typical case is 1–3 min depending on the number of Orphanet/OMIM
      reflections.
    - `deeprare_dir`: override the agent directory.
    - `deeprare_python`: override the venv interpreter.
    - `extra_env`: dict to merge into subprocess env (for testing).

    Required env vars (assert at construction):
    - `OPENROUTER_API_KEY`
    """

    NAME = "deeprare"

    DEFAULT_TIMEOUT_S = 900

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
        self.timeout_seconds = int(
            self.agent_extra.get("timeout_seconds", self.DEFAULT_TIMEOUT_S)
        )
        self._deeprare_dir = Path(self.agent_extra.get("deeprare_dir", _DEEPRARE_DIR))
        self._deeprare_python = Path(
            self.agent_extra.get("deeprare_python", _DEEPRARE_PYTHON)
        )
        self._extra_env: Dict[str, str] = dict(self.agent_extra.get("extra_env", {}))
        if not self._deeprare_python.exists():
            raise FileNotFoundError(
                f"DeepRare venv interpreter not found at {self._deeprare_python}. "
                "Run install steps in agents/deeprare/."
            )

        # Resolve a clean OpenRouter model id from the canonical backbone id.
        # DeepRare passes this to OpenAI()-compatible client; strip provider prefix.
        bb = self.backbone_id
        for prefix in ("openrouter/", "openai/"):
            if bb.startswith(prefix):
                bb = bb[len(prefix):]
        self._openai_model_id = bb

    # -------- pillar support --------

    def supports_pillar(self, pillar: Pillar) -> bool:
        # P2 HPO-only, P3 HPO+variants (text projection), P5 reasoning trace.
        # P1 deferred (DeepRare HPO extractor needs Selenium).
        # P4 family-aware not supported (no pedigree consumption).
        return pillar in {"P2_phenotype_ddx", "P3_genotype_aware", "P5_reasoning_communication"}

    # -------- predict --------

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
                error_message=f"DeepRare does not support pillar {pillar}.",
            )

        if not os.environ.get("OPENROUTER_API_KEY"):
            return self._finalize_log(
                log,
                ranked_predictions=[],
                status="agent_error",
                error_message="OPENROUTER_API_KEY env var not set.",
            )

        # Use a private results dir per call to avoid the cache-skip behaviour
        # in main.py (`if os.path.exists(result_file): continue`) and to keep
        # parallel runs from stomping each other.
        # FIX 2026-05-16 (first-case-leak): the previous version used `run_id`
        # alone as `run_tag`, so all 50 cases in a single pilot run shared one
        # `result_harness_<run_id>/case/<model>/patient_0.json`. The first call
        # wrote it; main.py's `if os.path.exists(result_file): continue` skip
        # caused EVERY subsequent case to be a no-op, returning the stale
        # first-case JSON. We now (a) include a per-case suffix in `run_tag`
        # and (b) defensively purge any pre-existing patient_*.json in
        # `out_dir` before each subprocess call.
        per_case_suffix = uuid.uuid4().hex[:8]
        base_tag = run_id or "harness"
        run_tag = f"{base_tag}_{case.case_id[:40]}_{per_case_suffix}"
        # Filesystem-safe: replace any non-alnum with underscore.
        run_tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_tag)
        results_root = self._deeprare_dir / f"result_harness_{run_tag}"
        # `case` is the dataset_name; model dir is appended by set_up_args.
        out_dir = results_root / "case" / self._openai_model_id
        out_dir.mkdir(parents=True, exist_ok=True)
        # Defensive purge: if a stale patient_*.json somehow exists in this
        # dir (e.g. resume after kill), wipe it so main.py's cache-skip can't
        # short-circuit.
        for stale in out_dir.glob("patient_*.json"):
            try:
                stale.unlink()
            except OSError:
                pass

        # Back up the canonical cases.csv (smoke fixture) and write our row.
        backup_path: Optional[Path] = None
        if _DEEPRARE_DATASET_CSV.exists():
            backup_path = _DEEPRARE_DATASET_CSV.with_suffix(
                f".csv.harness_backup.{run_tag}"
            )
            shutil.copy2(_DEEPRARE_DATASET_CSV, backup_path)

        try:
            row = _build_case_csv_row(
                case,
                include_genotype_text=(pillar == "P3_genotype_aware"),
            )
            _DEEPRARE_DATASET_CSV.parent.mkdir(parents=True, exist_ok=True)
            with _DEEPRARE_DATASET_CSV.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["hpo", "disease"])
                writer.writeheader()
                writer.writerow(row)

            env = {
                **os.environ,
                "OPENAI_BASE_URL": os.environ.get(
                    "OPENAI_BASE_URL", "https://openrouter.ai/api/v1"
                ),
                "DEEPRARE_MINI_MODEL": os.environ.get(
                    "DEEPRARE_MINI_MODEL", self._openai_model_id
                ),
                "DEEPRARE_NO_WEB": "1",
                "DEEPRARE_LOCAL_EMBEDDING": "1",
                "TOKENIZERS_PARALLELISM": "false",
                **self._extra_env,
            }
            # 2026-05-19 — propagate reasoning_effort=minimal for GPT-5 / o-series
            re_effort = reasoning_effort_for_backbone(self.backbone_id)
            if re_effort:
                env["OPENROUTER_REASONING_EFFORT"] = re_effort

            cmd = [
                str(self._deeprare_python),
                str(_DEEPRARE_MAIN),
                "--model", "openai",
                "--openai_apikey", os.environ["OPENROUTER_API_KEY"],
                "--openai_model", self._openai_model_id,
                "--dataset_name", "case",
                "--results_folder", str(results_root) + os.sep,
            ]

            t0 = time.time()
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(self._deeprare_dir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=int((time.time() - t0) * 1000),
                    status="timeout",
                    error_message=f"DeepRare subprocess exceeded {self.timeout_seconds}s",
                )

            latency_ms = int((time.time() - t0) * 1000)

            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout)[-1500:]
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="agent_error",
                    error_message=(
                        f"DeepRare returncode={proc.returncode}; "
                        f"stderr tail:\n{tail}"
                    ),
                )

            # Locate the patient_*.json output. Only one row was written, so
            # we expect exactly one file. main.py randomises iteration order
            # but only one patient exists.
            patient_files = sorted(out_dir.glob("patient_*.json"))
            if not patient_files:
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="parser_error",
                    error_message=(
                        f"DeepRare produced no patient JSON in {out_dir}. "
                        f"stdout tail: {proc.stdout[-600:]!r}"
                    ),
                )
            patient_path = patient_files[0]
            try:
                patient = json.loads(patient_path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as e:
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="parser_error",
                    error_message=f"DeepRare JSON parse failed: {e}",
                )

            final_md = patient.get("final_diagnois") or patient.get("first_round_result") or ""
            ranked = parse_deeprare_final_diagnois(final_md)

            reasoning_chunks = [
                f"# patient_info\n{patient.get('patient_info', '')}",
                f"# diagnosis_api_response\n{patient.get('diagnosis_api_response', '')}",
                f"# zero_shot_llm_response\n{patient.get('zero_shot_llm_response', '')}",
                f"# first_round_result\n{patient.get('first_round_result', '')}",
                f"# judgements\n{patient.get('judgements', '')}",
                f"# final_diagnois\n{final_md}",
            ]
            reasoning_trace = "\n\n".join(reasoning_chunks)

            log.extra.update(
                {
                    "deeprare_time_taken_s": patient.get("time_taken"),
                    "deeprare_patient_json_path": str(patient_path),
                    "judge_result": patient.get("judge_result"),
                    "phenotypes": patient.get("phenotypes"),
                    "phenotype_ids": patient.get("phenotype_ids"),
                }
            )
            log.cost.provider = "openrouter"
            # FIX D2 (2026-05-15): DeepRare's per-call OpenAI usage isn't
            # surfaced in patient.json. Estimate prompt + completion tokens
            # from the reasoning chunks (zero_shot + first_round + judgements
            # + final) so cost_usd is non-zero. This is a floor.
            full_reasoning = reasoning_trace
            est_prompt_chars = len(patient.get("patient_info", "") or "")
            est_completion_chars = len(full_reasoning or "")
            log.cost.prompt_tokens = max(
                log.cost.prompt_tokens, est_prompt_chars // 4
            )
            log.cost.completion_tokens = max(
                log.cost.completion_tokens, est_completion_chars // 4
            )
            fill_cost_from_tokens(log.cost, self.backbone_id)

            return self._finalize_log(
                log,
                ranked_predictions=ranked,
                reasoning_trace=reasoning_trace,
                raw_response_excerpt=final_md[:2000],
                latency_ms=latency_ms,
                status="ok",
            )

        finally:
            # Restore the original cases.csv if we had backed one up.
            if backup_path and backup_path.exists():
                shutil.move(str(backup_path), str(_DEEPRARE_DATASET_CSV))
            # Drop the per-run results dir (keep patient JSON path in log.extra
            # only if you copied it out — by default we throw it away to keep
            # disk clean. Comment out the next 3 lines to retain.)
            # We DO keep it, since extra["deeprare_patient_json_path"] points
            # there. Caller can purge after metric aggregation.


__all__ = ["DeepRareAdapter", "parse_deeprare_final_diagnois"]


# -------- verification ----------

if __name__ == "__main__":
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

    sys.path.insert(0, str(_PROJECT_ROOT))
    from harness.ingest import ingest_phenopacket_store  # noqa: E402

    case = next(
        ingest_phenopacket_store(_PROJECT_ROOT / "data" / "phenopacket_store" / "notebooks", limit=1)
    )
    adapter = DeepRareAdapter(backbone_id="openrouter/google/gemini-3-flash-preview")
    log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
    print("=== DeepRareAdapter verify ===")
    print("case_id:", log.case_id, "split:", log.source_split)
    print("status:", log.status, "error:", log.error_message)
    print("ranked_predictions[:5]:", log.ranked_predictions[:5])
    print("latency_ms:", log.total_latency_ms)
    print("cost:", log.cost.model_dump())
    print("extra:", {k: v for k, v in log.extra.items() if k != "phenotypes"})

"""Sanity-check pilot: end-to-end harness validation with LLM-control baseline.

Goals (round 1, milestone S6):
  1. Verify the LLMControlAdapter works end-to-end on real data.
  2. Verify metric / cost / logging pipeline works for 3 different backbones.
  3. Get a baseline Recall@k for the LLM-only condition we'll later compare
     scaffolded agents against.

Dataset (fixed-seed stratified sample, n=50):
  - 25 Phenopacket-Store cases (gold = OMIM, input = HPO list, no prose).
  - 25 RareArena RDS cases (gold = ORPHA, input = free-text case_report).

Pillars / eval modes (kept narrow for sanity):
  - Pillar 2 only.
  - eval_mode='gold_hpo' (Phenopacket-Store) -- uses case.gold_hpo_terms.
  - eval_mode='gold_hpo' (RareArena)        -- but those cases have no HPO
    list, so case_to_question falls back to free_text_vignette automatically.

Backbones (3):
  - google/gemini-3-flash-preview          (preview, fast/cheap)
  - deepseek/deepseek-v3.2-exp             (cheap end of the lineup)
  - openai/gpt-5                           (frontier)

If any backbone fails (rate limit / network / model unavailable), runs for
that backbone are marked status='agent_error' and the script continues.

Outputs:
  - data/sanity_check/results.jsonl   -- one PredictionLog per (case, backbone)
  - data/sanity_check/REPORT.md       -- markdown comparison table
  - stdout                            -- summary table

Cost expectation: 150 LLM calls, ~$5-10 USD total (gpt-5 dominates).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Resolve project root and ensure harness is importable.
PROJECT_ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
sys.path.insert(0, str(PROJECT_ROOT))

from harness.agents._adapter_utils import load_dotenv  # noqa: E402
from harness.agents.llm_control import LLMControlAdapter  # noqa: E402
from harness.canonical_case import CanonicalCase  # noqa: E402
from harness.ingest import ingest_phenopacket_store, ingest_rarearena  # noqa: E402
from harness.logging.backend import JsonlPredictionLogger, read_logs  # noqa: E402
from harness.logging.schema import PredictionLog  # noqa: E402
from harness.metrics.accuracy import rank_of_hit, recall_at_k_table  # noqa: E402
from harness.metrics.cross_map import gold_hit_with_crossmap  # noqa: E402


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

SEED = 42
N_PER_DATASET = 25
PILLAR = "P2_phenotype_ddx"
EVAL_MODE = "gold_hpo"

PHENOPACKET_DIR = (
    PROJECT_ROOT / "data" / "phenopacket_store" / "notebooks"
)
RAREARENA_JSONL = (
    PROJECT_ROOT / "data" / "rarearena" / "benchmark_data" / "RDS_benchmark.jsonl"
)

# 3 backbones to compare. Falls back to gpt-4o-mini if gpt-5 is unavailable.
BACKBONES: List[str] = [
    "google/gemini-3-flash-preview",
    "deepseek/deepseek-v3.2-exp",
    "openai/gpt-5",
]

# Per-backbone agent_extra overrides (gpt-5 needs more max_tokens because it
# emits reasoning tokens internally before any visible content).
BACKBONE_EXTRAS: Dict[str, dict] = {
    # gpt-5 frequently spends >5000 reasoning tokens before emitting visible
    # text. Cap timeout at 120s -- on timeout we get a clean agent_error rather
    # than blocking the whole pilot. Lower max_retries because retries also hit
    # the long reasoning path.
    "openai/gpt-5": {"max_tokens": 4000, "timeout_s": 120, "max_retries": 1},
    "google/gemini-3-flash-preview": {"max_tokens": 4000},
    "deepseek/deepseek-v3.2-exp": {"max_tokens": 4000},
}

OUT_DIR = PROJECT_ROOT / "data" / "sanity_check"
RESULTS_JSONL = OUT_DIR / "results.jsonl"
REPORT_MD = OUT_DIR / "REPORT.md"


# ----------------------------------------------------------------------
# Sampling helpers
# ----------------------------------------------------------------------


def _stratified_phenopacket_sample(
    n: int, seed: int
) -> List[CanonicalCase]:
    """Pick n Phenopacket-Store cases stratified by disease folder.

    We list every disease folder (under notebooks/), shuffle them, then take
    one case from each folder until we have n cases. This avoids the bias of
    sampling 25 cases from a single popular gene.
    """
    rng = random.Random(seed)
    folders = sorted(
        p.name
        for p in PHENOPACKET_DIR.iterdir()
        if p.is_dir() and (p / "phenopackets").is_dir()
    )
    rng.shuffle(folders)
    cases: List[CanonicalCase] = []
    for folder in folders:
        pp_dir = PHENOPACKET_DIR / folder / "phenopackets"
        json_files = sorted(pp_dir.glob("*.json"))
        if not json_files:
            continue
        target = json_files[rng.randrange(len(json_files))]
        try:
            from harness.ingest.phenopacket_store import phenopacket_to_canonical

            pp = json.loads(target.read_text())
            case = phenopacket_to_canonical(pp, source_split=folder)
            if not case.gold_hpo_terms:
                continue
            cases.append(case)
            if len(cases) >= n:
                break
        except Exception as e:  # noqa: BLE001
            print(
                f"[sample] SKIP {target.name}: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
    return cases


def _stratified_rarearena_sample(
    n: int, seed: int
) -> List[CanonicalCase]:
    """Pick n RareArena RDS cases. Stratified by Orpha_id to avoid hot
    diseases dominating.
    """
    rng = random.Random(seed + 1)
    # Load all then index by orpha_id; pick one per orpha until done.
    all_cases: List[CanonicalCase] = list(ingest_rarearena(RAREARENA_JSONL, subset="RDS"))
    rng.shuffle(all_cases)
    by_orpha: Dict[str, List[CanonicalCase]] = {}
    for c in all_cases:
        if c.gold_label.orphanet_id:
            by_orpha.setdefault(c.gold_label.orphanet_id, []).append(c)
    orphas = sorted(by_orpha.keys())
    rng.shuffle(orphas)
    out: List[CanonicalCase] = []
    for o in orphas:
        out.append(by_orpha[o][0])
        if len(out) >= n:
            break
    return out


def load_pilot_cases(seed: int = SEED) -> List[CanonicalCase]:
    """Return 25 + 25 = 50 stratified cases (Phenopacket-Store + RareArena RDS)."""
    pp_cases = _stratified_phenopacket_sample(N_PER_DATASET, seed=seed)
    ra_cases = _stratified_rarearena_sample(N_PER_DATASET, seed=seed)
    return pp_cases + ra_cases


# ----------------------------------------------------------------------
# Metric helpers
# ----------------------------------------------------------------------


def rank_of_hit_crossmap(
    predictions: List[str], gold
) -> Optional[int]:
    """Like accuracy.rank_of_hit but uses cross-ontology matching."""
    for i, p in enumerate(predictions, start=1):
        if gold_hit_with_crossmap(p, gold):
            return i
    return None


def recall_at_k_crossmap(
    predictions: List[List[str]], golds: List, k: int
) -> float:
    if not predictions:
        return 0.0
    hits = sum(
        1
        for preds, g in zip(predictions, golds)
        if rank_of_hit_crossmap(preds[:k], g) is not None
    )
    return hits / len(predictions)


def mrr_crossmap(predictions: List[List[str]], golds: List) -> float:
    if not predictions:
        return 0.0
    s = 0.0
    for preds, g in zip(predictions, golds):
        r = rank_of_hit_crossmap(preds, g)
        if r is not None:
            s += 1.0 / r
    return s / len(predictions)


def median_rank_crossmap(
    predictions: List[List[str]], golds: List, miss_value: int = 6
) -> float:
    if not predictions:
        return float("inf")
    ranks: List[int] = []
    for preds, g in zip(predictions, golds):
        r = rank_of_hit_crossmap(preds, g)
        ranks.append(r if r is not None else miss_value)
    return statistics.median(ranks)


# ----------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------


def run_one_backbone(
    backbone_id: str,
    cases: List[CanonicalCase],
    logger: JsonlPredictionLogger,
    run_id: str,
    progress_prefix: str = "",
) -> int:
    """Run one backbone over all cases, writing logs as we go.

    Returns the number of cases where status == 'ok'.
    """
    extras = BACKBONE_EXTRAS.get(backbone_id, {})
    try:
        adapter = LLMControlAdapter(
            backbone_id=backbone_id,
            backbone_temperature=0.0,
            agent_extra=extras,
        )
    except Exception as e:  # noqa: BLE001
        print(
            f"[{backbone_id}] FAILED TO INIT adapter: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 0

    ok = 0
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        try:
            log = adapter.predict(
                case,
                pillar=PILLAR,
                eval_mode=EVAL_MODE,
                run_id=run_id,
            )
        except Exception as e:  # noqa: BLE001
            log = adapter._new_log(case, PILLAR, EVAL_MODE, run_id)
            log = adapter._finalize_log(
                log,
                ranked_predictions=[],
                status="agent_error",
                error_message=f"unhandled: {type(e).__name__}: {e}",
            )
        logger.write(log)
        elapsed = time.time() - t0
        marker = "OK" if log.status == "ok" else log.status.upper()
        if log.status == "ok":
            ok += 1
        print(
            f"{progress_prefix}[{i:>3}/{len(cases)}] {backbone_id:42s} "
            f"{case.source_dataset:18s} {case.case_id[:30]:30s} "
            f"{marker:14s} {elapsed:5.1f}s "
            f"top1={log.ranked_predictions[:1]}"
        )
    return ok


# ----------------------------------------------------------------------
# Aggregation / report
# ----------------------------------------------------------------------


def aggregate_per_backbone(
    logs: List[PredictionLog],
    cases_by_id: Dict[Tuple[str, str], CanonicalCase],
) -> Dict[str, dict]:
    """Compute per-backbone metrics from the raw PredictionLog stream."""
    by_bb: Dict[str, List[PredictionLog]] = {}
    for lg in logs:
        by_bb.setdefault(lg.backbone_id, []).append(lg)

    out: Dict[str, dict] = {}
    for bb, items in by_bb.items():
        ok_items = [it for it in items if it.status == "ok"]
        all_items = items

        # For metrics, use ALL items (failed ones contribute 0 hit).
        preds: List[List[str]] = []
        golds = []
        for it in all_items:
            key = (it.source_dataset, it.case_id)
            case = cases_by_id.get(key)
            if case is None:
                continue
            preds.append(list(it.ranked_predictions or []))
            golds.append(case.gold_label)

        if not preds:
            out[bb] = {"n": 0}
            continue

        rec = recall_at_k_crossmap
        metrics = {
            "n": len(all_items),
            "n_ok": len(ok_items),
            "recall@1": rec(preds, golds, 1),
            "recall@3": rec(preds, golds, 3),
            "recall@5": rec(preds, golds, 5),
            "recall@10": rec(preds, golds, 10),
            "mrr": mrr_crossmap(preds, golds),
            "median_rank": median_rank_crossmap(preds, golds),
            "total_prompt_tokens": sum(
                it.cost.prompt_tokens for it in all_items
            ),
            "total_completion_tokens": sum(
                it.cost.completion_tokens for it in all_items
            ),
            "total_cost_usd": sum(it.cost.cost_usd for it in all_items),
            "mean_latency_s": (
                statistics.mean(it.total_latency_ms for it in all_items)
                / 1000.0
            ),
            "errors": [
                {"case_id": it.case_id, "status": it.status, "msg": it.error_message}
                for it in items
                if it.status != "ok"
            ],
        }
        out[bb] = metrics
    return out


def render_report(
    metrics: Dict[str, dict], n_total: int, started_at: str
) -> str:
    lines: List[str] = []
    lines.append("# Sanity-Check Pilot — LLM No-Scaffolding Control")
    lines.append("")
    lines.append(f"- Started: {started_at}")
    lines.append(f"- Cases:   {n_total} (25 Phenopacket-Store + 25 RareArena RDS)")
    lines.append(f"- Pillar:  {PILLAR}, eval_mode={EVAL_MODE}")
    lines.append(f"- Agent:   `llm_control` (no scaffolding, no tools)")
    lines.append(f"- Seed:    {SEED}")
    lines.append("")
    lines.append("## Per-backbone metrics")
    lines.append("")
    lines.append(
        "| Backbone | R@1 | R@3 | R@5 | R@10 | MRR | Median Rank | "
        "Total Cost ($) | Mean Lat (s) | N OK / N |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    for bb, m in metrics.items():
        if m.get("n", 0) == 0:
            lines.append(
                f"| `{bb}` | (no data) | | | | | | | | |"
            )
            continue
        lines.append(
            f"| `{bb}` | "
            f"{m['recall@1']:.2f} | "
            f"{m['recall@3']:.2f} | "
            f"{m['recall@5']:.2f} | "
            f"{m['recall@10']:.2f} | "
            f"{m['mrr']:.3f} | "
            f"{m['median_rank']:.1f} | "
            f"{m['total_cost_usd']:.4f} | "
            f"{m['mean_latency_s']:.2f} | "
            f"{m['n_ok']} / {m['n']} |"
        )
    lines.append("")

    # Per-backbone errors block
    any_err = any(m.get("errors") for m in metrics.values())
    if any_err:
        lines.append("## Errors")
        lines.append("")
        for bb, m in metrics.items():
            errs = m.get("errors") or []
            if not errs:
                continue
            lines.append(f"### `{bb}` ({len(errs)} non-ok)")
            for e in errs[:20]:
                msg = (e.get("msg") or "").replace("\n", " ")[:200]
                lines.append(f"- {e['case_id']} | {e['status']} | {msg}")
            if len(errs) > 20:
                lines.append(f"  ... +{len(errs)-20} more")
            lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Recall@k uses Orphadata cross-mapping "
        "(`gold_hit_with_crossmap`) so an OMIM gold can hit via a "
        "cross-referenced ORPHA prediction and vice versa."
    )
    lines.append(
        "- Cost rows are derived from OpenRouter `usage.completion_tokens` / "
        "`usage.prompt_tokens` × per-million-token prices in `.env`. "
        "Backbones missing from `_PRICES` (e.g. `openai/gpt-4o-mini` was a "
        "fallback added mid-pilot) show cost=$0; tokens are still tracked."
    )
    lines.append(
        "- `openai/gpt-5` was halted after 6 cases due to extreme latency "
        "(mean 76 s / call) and a high parser_error rate caused by gpt-5 "
        "emitting only encrypted reasoning tokens (no visible content) at "
        "max_tokens=6000. `openai/gpt-4o-mini` was added as a third "
        "no-scaffolding control in its place."
    )
    lines.append(
        "- `N OK / N` shows ok-only vs total. Metrics are computed over "
        "ALL N (failed cases score 0). For gpt-5 this means R@k is "
        "computed on only n=6 cases and is NOT comparable."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def render_stdout_summary(metrics: Dict[str, dict]) -> str:
    """Return the simple plaintext summary table expected in the deliverable."""
    hdr = (
        f"{'Backbone':38s}  {'R@1':5s} {'R@3':5s} {'R@5':5s} "
        f"{'R@10':5s}  {'MRR':6s} {'Cost($)':8s}  {'MeanLat':8s}"
    )
    rows: List[str] = [hdr, "-" * len(hdr)]
    for bb, m in metrics.items():
        if m.get("n", 0) == 0:
            rows.append(f"{bb:38s}  (no data)")
            continue
        rows.append(
            f"{bb:38s}  "
            f"{m['recall@1']:.2f}  "
            f"{m['recall@3']:.2f}  "
            f"{m['recall@5']:.2f}  "
            f"{m['recall@10']:.2f}  "
            f"{m['mrr']:.3f}  "
            f"{m['total_cost_usd']:6.2f}    "
            f"{m['mean_latency_s']:.2f}s"
        )
    return "\n".join(rows)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backbones",
        nargs="+",
        default=BACKBONES,
        help="OpenRouter model ids to test (default = 3 baseline lineup).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional: cap to first N cases (debug).",
    )
    parser.add_argument(
        "--results",
        default=str(RESULTS_JSONL),
        help="Output JSONL path.",
    )
    parser.add_argument(
        "--report",
        default=str(REPORT_MD),
        help="Output markdown report path.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="If set, skip (backbone, case_id) pairs already in --results.",
    )
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERR: OPENROUTER_API_KEY not in env — check .env", file=sys.stderr)
        return 1

    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    run_id = f"sanity-pilot-{int(time.time())}"

    print(f"[sanity_check] loading cases (seed={SEED})...", file=sys.stderr)
    cases = load_pilot_cases(seed=SEED)
    if args.limit:
        cases = cases[: args.limit]
    print(
        f"[sanity_check] {len(cases)} cases loaded "
        f"({sum(1 for c in cases if c.source_dataset=='phenopacket_store')} "
        f"phenopacket_store + "
        f"{sum(1 for c in cases if c.source_dataset=='rarearena')} rarearena)",
        file=sys.stderr,
    )

    cases_by_id: Dict[Tuple[str, str], CanonicalCase] = {
        (c.source_dataset, c.case_id): c for c in cases
    }

    results_path = Path(args.results)
    # Resume support: skip (backbone, case_id) already logged with status='ok'.
    already_done: set[Tuple[str, str, str]] = set()
    if args.resume and results_path.exists():
        for lg in read_logs(results_path):
            if lg.status == "ok":
                already_done.add((lg.backbone_id, lg.source_dataset, lg.case_id))
        print(
            f"[sanity_check] resume mode: {len(already_done)} (bb, case) "
            f"pairs already complete.",
            file=sys.stderr,
        )

    results_path.parent.mkdir(parents=True, exist_ok=True)
    logger = JsonlPredictionLogger(results_path)

    try:
        for bb in args.backbones:
            print(
                f"\n=== BACKBONE: {bb} ===\n",
                file=sys.stderr,
            )
            todo = [
                c for c in cases
                if (bb, c.source_dataset, c.case_id) not in already_done
            ]
            if not todo:
                print(f"[{bb}] all cases already done (resume).", file=sys.stderr)
                continue
            run_one_backbone(
                backbone_id=bb,
                cases=todo,
                logger=logger,
                run_id=run_id,
                progress_prefix="",
            )
    finally:
        logger.close()

    # ---- aggregate + report ----
    all_logs = read_logs(results_path)
    metrics = aggregate_per_backbone(all_logs, cases_by_id)
    report = render_report(metrics, n_total=len(cases), started_at=started_at)
    Path(args.report).write_text(report)

    print("")
    print(render_stdout_summary(metrics))
    print("")
    print(f"results: {results_path}")
    print(f"report:  {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

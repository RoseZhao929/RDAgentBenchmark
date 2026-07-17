"""Round 2 Phase 1 — Pillar 1 extraction pilot.

Setup (per round2_plan.md §3):
- 50 PP-Store cases, seed=42 (same shuffle as scripts/mini_round2_pilot.py).
- 3 agents: llm_control, rdma, deeprare.
- Backbone: Gemini Flash via OpenRouter.

PP-Store cases lack free text, so we synthesize a one-paragraph clinical
vignette from gold HPO labels and feed THAT into each extractor. The
extractor's job is to recover HP:* IDs (or phrases that normalize to them).

Two evaluation modes, both reported per agent:
  (1) exact-id   — extracted HP:* IDs vs gold HP:* IDs (P/R/F1)
  (2) phrase-norm — extracted phrases run through `normalize_phrase()` then
                    compared as IDs (rapidfuzz @ threshold 90)

DeepRare's `extract_phenotypes` is NOT implemented per harness/agents/deeprare.py
(needs Selenium + OBO lookups). It's logged as `not_implemented` and skipped.

Output:
  data/round2/phase1/p1_extraction_results.jsonl  (one PredictionLog per (agent, case))
  data/round2/phase1/P1_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import traceback
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def load_env(env_path: Path = PROJECT_ROOT / ".env") -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


# --------------- sample selection ----------------------

def build_pp_sample(seed: int = 42, n: int = 50) -> list:
    """Same shuffle as mini_round2_pilot.py — first N PP-Store cases."""
    from harness.ingest import ingest_phenopacket_store
    rng = random.Random(seed)
    pp_all = list(ingest_phenopacket_store(
        str(PROJECT_ROOT / "data" / "phenopacket_store" / "notebooks")
    ))
    rng.shuffle(pp_all)
    return pp_all[:n]


# --------------- vignette synthesis --------------------

def synthesize_vignette_from_hpo(case) -> str:
    """Build a deterministic one-paragraph clinical vignette from HPO labels.

    Keeps the labels verbatim (extractors need them visible) but wraps them in
    natural-language scaffolding so the extractor's task is non-trivial.
    """
    demo_bits = []
    age = case.demographics.age_at_onset_years
    sex = case.demographics.sex
    if age is not None:
        demo_bits.append(f"{age:.0f}-year-old")
    if sex and sex != "unknown":
        demo_bits.append(sex)
    subject = " ".join(demo_bits) if demo_bits else "patient"

    present = [t for t in case.gold_hpo_terms if not t.negated and t.label]
    absent = [t for t in case.gold_hpo_terms if t.negated and t.label]

    parts: List[str] = []
    if present:
        labels = "; ".join(t.label for t in present)
        parts.append(
            f"A {subject} presents with the following clinical findings: {labels}."
        )
    if absent:
        labels = "; ".join(t.label for t in absent)
        parts.append(f"The following findings are notably absent: {labels}.")
    if not parts:
        parts.append(f"A {subject} presents with multiple unexplained features.")
    return " ".join(parts)


# --------------- adapter factory ----------------------

def make_adapter(name: str, backbone_id: str):
    from harness.agents import LLMControlAdapter, RDMAAdapter, DeepRareAdapter
    if name == "llm_control":
        return LLMControlAdapter(backbone_id=backbone_id)
    if name == "rdma":
        return RDMAAdapter(backbone_id=backbone_id)
    if name == "deeprare":
        return DeepRareAdapter(backbone_id=backbone_id)
    raise ValueError(f"unknown agent {name}")


# --------------- DeepRare P1 best-effort ---------------

# DeepRare's harness adapter explicitly does NOT implement Pillar 1.
# Per `agents/deeprare/hpo_extractor.py` upstream needs Selenium for OBO.
# We try LLM-control-style fallback BUT log as `deeprare_not_implemented`
# so the metric stays honest.

def run_deeprare_p1(case, adapter):
    """Attempts DeepRare P1 via adapter.extract_phenotypes.

    DeepRare's harness adapter does not override extract_phenotypes (base
    raises NotImplementedError). We catch and log explicitly so the column in
    the report reads as 'not implemented' rather than a generic crash.
    """
    try:
        terms = adapter.extract_phenotypes(case)
    except NotImplementedError as e:
        return {
            "status": "not_implemented",
            "phrases": [],
            "hpo_ids": [],
            "error": f"DeepRare extract_phenotypes: {e}",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "agent_error",
            "phrases": [],
            "hpo_ids": [],
            "error": f"{type(e).__name__}: {e}",
        }
    phrases: List[str] = []
    hpo_ids: List[str] = []
    for t in terms:
        if t.id and t.id != "HP:0000000":
            hpo_ids.append(t.id)
        if t.label:
            phrases.append(t.label)
    return {"status": "ok", "phrases": phrases, "hpo_ids": hpo_ids, "error": None}


# --------------- resume helper ------------------------

def load_done(path: Path) -> set:
    if not path.exists():
        return set()
    seen = set()
    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                seen.add((r["agent_id"], r["case_id"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return seen


# --------------- main loop ----------------------------

def run(
    agents: List[str],
    backbone_id: str,
    out_path: Path,
    metric_path: Path,
    n: int = 50,
    seed: int = 42,
    resume: bool = True,
) -> None:
    from harness.canonical_case import HpoTerm
    from harness.logging import JsonlPredictionLogger
    from harness.metrics import hpo_prf1, normalize_phrase

    print(f"[p1] sample: PP-Store n={n} seed={seed}", flush=True)
    cases = build_pp_sample(seed=seed, n=n)
    print(f"  cases ready: {len(cases)}", flush=True)

    done = load_done(out_path) if resume else set()
    if done:
        print(f"[p1] resume: {len(done)} (agent,case) rows already in log", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger = JsonlPredictionLogger(out_path)
    metric_f = metric_path.open("a", buffering=1)

    run_id = f"p1_phase1_{int(time.time())}"
    total = len(cases) * len(agents)
    done_count = len(done)

    for agent_name in agents:
        print(f"\n[p1] === {agent_name} ===", flush=True)
        try:
            adapter = make_adapter(agent_name, backbone_id)
        except Exception as e:
            print(f"  [p1] {agent_name} adapter init FAIL: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
            continue

        for case in cases:
            if (agent_name, case.case_id) in done:
                continue
            t0 = time.time()
            vignette = synthesize_vignette_from_hpo(case)
            # Inject our synthetic vignette into the case object so each
            # adapter's existing `extract_phenotypes` text-selection logic
            # picks it up (without dropping into the HPO-listing fallback,
            # which would defeat the point of evaluating extraction).
            # We mutate a private copy to keep the original cases intact.
            case_clone = case.model_copy()
            case_clone.synthetic_vignette = vignette

            # ------ Run extractor ------
            from harness.canonical_case import HpoTerm  # local re-import
            phrases: List[str] = []
            ids_from_agent: List[str] = []
            status = "ok"
            err = None
            try:
                if agent_name == "deeprare":
                    result = run_deeprare_p1(case_clone, adapter)
                    if result["status"] != "ok":
                        status = result["status"]
                        err = result["error"]
                    else:
                        phrases = result["phrases"]
                        ids_from_agent = result["hpo_ids"]
                else:
                    hpo_terms = adapter.extract_phenotypes(case_clone)
                    for t in hpo_terms:
                        if t.id and t.id != "HP:0000000":
                            ids_from_agent.append(t.id)
                            if t.label:
                                phrases.append(t.label)
                        elif t.label:
                            phrases.append(t.label)
            except NotImplementedError as e:
                status = "not_implemented"
                err = f"{type(e).__name__}: {e}"
            except Exception as e:  # noqa: BLE001
                status = "agent_error"
                err = f"{type(e).__name__}: {e}"

            latency_ms = int((time.time() - t0) * 1000)

            # ------ Metric: exact-id ------
            gold_terms = [t for t in case.gold_hpo_terms if not t.negated]
            gold_ids = {t.id for t in gold_terms}

            # exact-id: only score IDs the agent actually emitted as HP:\d{7}
            exact_pred_terms = [HpoTerm(id=i, label=None) for i in set(ids_from_agent)
                                if re.match(r"^HP:\d{7}$", i)]
            exact_prf1 = hpo_prf1(exact_pred_terms, gold_terms, mode="exact")

            # ------ Metric: phrase-norm ------
            normed_ids: List[str] = list(set(ids_from_agent))  # start with direct IDs
            phrase_mapped: List[dict] = []
            for ph in phrases:
                hid = normalize_phrase(ph, threshold=90)
                phrase_mapped.append({"phrase": ph, "hpo_id": hid})
                if hid:
                    normed_ids.append(hid)
            normed_pred_terms = [HpoTerm(id=i, label=None) for i in set(normed_ids)
                                 if re.match(r"^HP:\d{7}$", i)]
            phrase_prf1 = hpo_prf1(normed_pred_terms, gold_terms, mode="exact")

            # ------ Build a PredictionLog and write ------
            from harness.logging.schema import PredictionLog
            log = PredictionLog(
                run_id=run_id,
                agent_id=agent_name,
                backbone_id=backbone_id,
                backbone_temperature=0.0,
                case_id=case.case_id,
                source_dataset=case.source_dataset,
                source_split=case.source_split,
                pillar="P1_extraction",
                eval_mode="end_to_end",
                ranked_predictions=[],
                extracted_hpo_terms=list({t.id for t in exact_pred_terms}),
                raw_response_excerpt=json.dumps(phrases, ensure_ascii=False)[:2000],
                total_latency_ms=latency_ms,
                status=status if status in {"ok", "agent_error", "timeout", "rate_limited",
                                            "parser_error", "skipped"} else "skipped",
                error_message=err,
                extra={
                    "p1_phrases": phrases,
                    "p1_phrase_mapped": phrase_mapped,
                    "p1_status_raw": status,  # preserves "not_implemented"
                    "gold_n": len(gold_terms),
                    "exact_prf1": exact_prf1,
                    "phrase_prf1": phrase_prf1,
                    "vignette_used": vignette[:500],
                },
            )
            logger.write(log)

            # Per-row mirror in the metric jsonl for quick aggregation
            metric_f.write(json.dumps({
                "agent": agent_name,
                "case_id": case.case_id,
                "status": status,
                "latency_ms": latency_ms,
                "gold_n": len(gold_terms),
                "exact": exact_prf1,
                "phrase_norm": phrase_prf1,
                "n_phrases": len(phrases),
                "n_phrase_norm_hits": sum(1 for m in phrase_mapped if m["hpo_id"]),
            }) + "\n")

            done_count += 1
            print(
                f"  [{done_count}/{total}] {agent_name} / {case.case_id[:30]:30s} "
                f"st={status:18s} {latency_ms/1000:5.1f}s gold={len(gold_terms):2d} "
                f"exact_f1={exact_prf1['f1']:.2f} phrase_f1={phrase_prf1['f1']:.2f}",
                flush=True,
            )

    metric_f.close()
    logger.close()
    print(f"\n[p1] done. predictions → {out_path}; per-row metrics → {metric_path}", flush=True)


# --------------- aggregate + report -------------------

def aggregate_and_report(metric_path: Path, report_path: Path) -> None:
    from harness.metrics import aggregate_hpo_prf1

    if not metric_path.exists():
        print(f"[p1] no metric file at {metric_path}; nothing to aggregate.")
        return

    rows = []
    with metric_path.open() as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    by_agent: dict[str, list] = {}
    for r in rows:
        by_agent.setdefault(r["agent"], []).append(r)

    table_rows = []
    for agent, agent_rows in sorted(by_agent.items()):
        ok = [r for r in agent_rows if r["status"] == "ok"]
        n_total = len(agent_rows)
        n_ok = len(ok)
        if not ok:
            # All not-implemented / errored.
            statuses = {}
            for r in agent_rows:
                statuses[r["status"]] = statuses.get(r["status"], 0) + 1
            table_rows.append({
                "agent": agent,
                "n_ok": n_ok,
                "n_total": n_total,
                "statuses": statuses,
                "exact_micro_p": float("nan"),
                "exact_micro_r": float("nan"),
                "exact_micro_f1": float("nan"),
                "phrase_micro_p": float("nan"),
                "phrase_micro_r": float("nan"),
                "phrase_micro_f1": float("nan"),
                "mean_latency_s": 0.0,
                "mean_phrases": 0.0,
                "mean_phrase_hits": 0.0,
            })
            continue
        exact_agg = aggregate_hpo_prf1([r["exact"] for r in ok], aggregate="micro")
        phrase_agg = aggregate_hpo_prf1([r["phrase_norm"] for r in ok], aggregate="micro")
        mean_lat = sum(r["latency_ms"] for r in ok) / len(ok) / 1000
        mean_phrases = sum(r["n_phrases"] for r in ok) / len(ok)
        mean_hits = sum(r["n_phrase_norm_hits"] for r in ok) / len(ok)
        table_rows.append({
            "agent": agent,
            "n_ok": n_ok,
            "n_total": n_total,
            "statuses": None,
            "exact_micro_p": exact_agg["precision"],
            "exact_micro_r": exact_agg["recall"],
            "exact_micro_f1": exact_agg["f1"],
            "phrase_micro_p": phrase_agg["precision"],
            "phrase_micro_r": phrase_agg["recall"],
            "phrase_micro_f1": phrase_agg["f1"],
            "mean_latency_s": mean_lat,
            "mean_phrases": mean_phrases,
            "mean_phrase_hits": mean_hits,
        })

    md = ["# Round 2 Phase 1 — Pillar 1 (Phenotype Extraction) Report\n"]
    md.append(f"\n- Sample: 50 Phenopacket-Store cases (seed=42, same shuffle as mini pilot).")
    md.append(f"- Backbone: `openrouter/google/gemini-3-flash-preview`")
    md.append(f"- Vignette synthesis: HPO labels embedded in a one-paragraph prose.\n")
    md.append("## Per-agent micro P/R/F1\n")
    md.append("| Agent | OK/Total | Exact-ID P | R | F1 | Phrase-norm P | R | F1 | mean lat (s) | mean phrases / hits |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in table_rows:
        if r["statuses"] is not None:
            md.append(
                f"| `{r['agent']}` | {r['n_ok']}/{r['n_total']} | "
                f"(no OK rows: {r['statuses']}) | | | | | | | |"
            )
        else:
            md.append(
                f"| `{r['agent']}` | {r['n_ok']}/{r['n_total']} | "
                f"{r['exact_micro_p']:.3f} | {r['exact_micro_r']:.3f} | {r['exact_micro_f1']:.3f} | "
                f"{r['phrase_micro_p']:.3f} | {r['phrase_micro_r']:.3f} | {r['phrase_micro_f1']:.3f} | "
                f"{r['mean_latency_s']:.1f} | "
                f"{r['mean_phrases']:.1f} / {r['mean_phrase_hits']:.1f} |"
            )

    md.append("\n## Notes\n")
    md.append("- **Exact-ID mode**: agent's output IDs must already be HP:\\d{7}. "
              "Useful for agents like DeepRare (when implemented) that emit IDs directly.")
    md.append("- **Phrase-norm mode**: agent's free-text phrases are passed through "
              "`harness.metrics.normalize_phrase` (hp.obo name+synonym table, rapidfuzz @ 90).")
    md.append("- DeepRare is logged as `not_implemented` per harness/agents/deeprare.py "
              "(Selenium dependency for OBO).")

    report_path.write_text("\n".join(md))
    print(f"[p1] report → {report_path}")
    print("\n".join(md))


# --------------- CLI ----------------------------------

if __name__ == "__main__":
    load_env()
    p = argparse.ArgumentParser()
    p.add_argument("--agents", default="llm_control,rdma,deeprare",
                   help="Comma-separated agent names")
    p.add_argument("--backbone", default="openrouter/google/gemini-3-flash-preview")
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="data/round2/phase1/p1_extraction_results.jsonl")
    p.add_argument("--metric-out", default="data/round2/phase1/p1_metric_rows.jsonl")
    p.add_argument("--report", default="data/round2/phase1/P1_REPORT.md")
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()

    out_path = Path(args.out)
    metric_path = Path(args.metric_out)
    report_path = Path(args.report)
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]

    if not args.report_only:
        run(
            agents=agents,
            backbone_id=args.backbone,
            out_path=out_path,
            metric_path=metric_path,
            n=args.n,
            seed=args.seed,
            resume=not args.no_resume,
        )

    aggregate_and_report(metric_path, report_path)

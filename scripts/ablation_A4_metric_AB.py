"""Ablation A4 — strict ID-match vs variants-aware ORPHA fuzzy A/B.

Re-aggregates Phase 4a predictions under two evaluator regimes:
  A. STRICT: gold_hit_with_crossmap (ID prefix + OMIM/ORPHA cross-map only)
  B. VARIANTS: gold_hit_with_variants on ranked_predictions_variants
     (adapter-side tied-ORPHA candidates from map_names_to_ids_with_variants)

Output:
  - data/round2/ablations/A4_metric_AB.md
  - data/round2/ablations/A4_metric_AB.json

Pre-registered as ablation A4. Compares the metric impact of the
fuzzy-tie fix (2026-05-19) on RareBench-style sibling-ORPHA cases.
"""
from __future__ import annotations
import sys, json, os, glob
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    from harness.canonical_case import CanonicalCase
    from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants
    from harness.ingest import ingest_phenopacket_store, ingest_rarearena, ingest_rarebench
    print("Loading gold maps...", file=sys.stderr)
    case_gold = {}
    for c in ingest_phenopacket_store('data/phenopacket_store/notebooks'): case_gold[c.case_id] = ('phenopacket_store', c.gold_label)
    for c in ingest_rarearena('data/rarearena/benchmark_data/RDS_benchmark.jsonl', 'RDS'): case_gold[c.case_id] = ('rarearena_rds', c.gold_label)
    for split in ('RAMEDIS','LIRICAL','MME','HMS'):
        for c in ingest_rarebench(f'data/rarebench_hf/data_unzipped/data/{split}.jsonl', split): case_gold[c.case_id] = ('rarebench', c.gold_label)
    with open('data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl') as f:
        for line in f:
            c = CanonicalCase.model_validate_json(line); case_gold[c.case_id] = ('mimic_diverse', c.gold_label)

    stats = defaultdict(lambda: {"ok":0,"h1_strict":0,"h1_variants":0,"h5_strict":0,"h5_variants":0})
    for p in sorted(glob.glob('data/round2/phase4a/predictions_*.jsonl')):
        fn = os.path.basename(p).replace('predictions_','').replace('.jsonl','')
        ds = ag = None
        for d in ('phenopacket_store','rarearena_rds','rarebench','mimic_diverse'):
            if fn.startswith(d+'_'): ds = d; rest = fn[len(d)+1:]; break
        if not ds: continue
        for a in ('mdagents','medagents','agentclinic','maidxo','deeprare','llm_control','vc_rdagent','lirical'):
            if rest.startswith(a+'_'): ag = a; bb = rest[len(a)+1:]; break
        if not ag: continue
        key = (ds, ag)
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                if r.get('status') != 'ok': continue
                stats[key]['ok'] += 1
                _, g = case_gold.get(r['case_id'], (None, None))
                if not g: continue
                preds = r.get('ranked_predictions', [])
                variants = r.get('extra', {}).get('ranked_predictions_variants') or []
                if preds and gold_hit_with_crossmap(preds[0], g): stats[key]['h1_strict'] += 1
                if any(gold_hit_with_crossmap(p, g) for p in preds[:5]): stats[key]['h5_strict'] += 1
                if variants and gold_hit_with_variants(variants[0], g): stats[key]['h1_variants'] += 1
                elif preds and gold_hit_with_crossmap(preds[0], g): stats[key]['h1_variants'] += 1
                if variants and any(gold_hit_with_variants(v, g) for v in variants[:5]): stats[key]['h5_variants'] += 1
                elif any(gold_hit_with_crossmap(p, g) for p in preds[:5]): stats[key]['h5_variants'] += 1

    # Build markdown table
    md = ["# Ablation A4 — Strict vs Variants ORPHA Fuzzy (cross-map metric A/B)",
          "",
          "Pre-registered ablation A4. Measures the impact of the 2026-05-19",
          "fuzzy-tie fix (`map_names_to_ids_with_variants`) on R@1/R@5 across",
          "Phase 4a (N=100 × 4 datasets).",
          "",
          "## Per-(dataset, agent) lift from STRICT → VARIANTS",
          "",
          "| Dataset | Agent | n_ok | R@1 strict | R@1 variants | Δ | R@5 strict | R@5 variants | Δ |",
          "|---|---|---|---|---|---|---|---|---|",
    ]
    totals = {"r1s":0, "r1v":0, "r5s":0, "r5v":0, "n":0}
    for (ds, ag), s in sorted(stats.items()):
        if s['ok'] == 0: continue
        n = s['ok']
        r1s, r1v = s['h1_strict']/n, s['h1_variants']/n
        r5s, r5v = s['h5_strict']/n, s['h5_variants']/n
        d1 = r1v - r1s
        d5 = r5v - r5s
        md.append(f"| {ds} | `{ag}` | {n} | {r1s:.2f} | **{r1v:.2f}** | {'+' if d1>=0 else ''}{d1:.2f} | {r5s:.2f} | **{r5v:.2f}** | {'+' if d5>=0 else ''}{d5:.2f} |")
        totals["r1s"] += s['h1_strict']; totals["r1v"] += s['h1_variants']
        totals["r5s"] += s['h5_strict']; totals["r5v"] += s['h5_variants']
        totals["n"] += n

    if totals["n"] > 0:
        md.append(f"\n## Aggregate")
        md.append(f"- Total predictions: {totals['n']}")
        md.append(f"- R@1 strict: {totals['r1s']/totals['n']:.3f}")
        md.append(f"- R@1 variants: {totals['r1v']/totals['n']:.3f}")
        md.append(f"- **Δ R@1**: +{(totals['r1v']-totals['r1s'])/totals['n']:.3f}")
        md.append(f"- R@5 strict: {totals['r5s']/totals['n']:.3f}")
        md.append(f"- R@5 variants: {totals['r5v']/totals['n']:.3f}")
        md.append(f"- **Δ R@5**: +{(totals['r5v']-totals['r5s'])/totals['n']:.3f}")

    Path('data/round2/ablations').mkdir(parents=True, exist_ok=True)
    Path('data/round2/ablations/A4_metric_AB.md').write_text("\n".join(md))
    Path('data/round2/ablations/A4_metric_AB.json').write_text(json.dumps({f"{k[0]}|{k[1]}": v for k, v in stats.items()}, indent=2))
    print(f"Wrote A4_metric_AB.md + A4_metric_AB.json")
    if totals["n"] > 0:
        print(f"Aggregate Δ R@1: +{(totals['r1v']-totals['r1s'])/totals['n']:.3f}")
        print(f"Aggregate Δ R@5: +{(totals['r5v']-totals['r5s'])/totals['n']:.3f}")

if __name__ == "__main__":
    main()

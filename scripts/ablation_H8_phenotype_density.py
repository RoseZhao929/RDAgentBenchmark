"""H8 — Phenotype density non-linearly predicts performance (inverted-U).

Pre-registered (plan.md): bin cases by # HPO terms (≤5, 6-15, 16-30, >30);
hypothesis = inverted-U — too few (under-specified) AND too many (noise/
distractors) both degrade R@1.

Test on HPO-input datasets (PP-Store, RareBench) where the HPO-term count is
the actual model input density. Pool over the strongest LLM cells + classical
baselines (Gemini Flash N=500 + lirical/vc_rdagent) to get per-bin R@1.

Output: data/round2/ablations/H8_phenotype_density.md
"""
from __future__ import annotations
import json, glob, os, sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants
    from harness.ingest import ingest_phenopacket_store, ingest_rarebench
    # gold + HPO count per case
    case_gold, case_nhpo = {}, {}
    for c in ingest_phenopacket_store('data/phenopacket_store/notebooks'):
        case_gold[c.case_id] = c.gold_label
        case_nhpo[c.case_id] = len(c.gold_hpo_terms or [])
    for split in ('RAMEDIS','LIRICAL','MME','HMS'):
        for c in ingest_rarebench(f'data/rarebench_hf/data_unzipped/data/{split}.jsonl', split):
            case_gold[c.case_id] = c.gold_label
            case_nhpo[c.case_id] = len(c.gold_hpo_terms or [])

    def bin_of(n):
        if n <= 5: return '≤5'
        if n <= 15: return '6-15'
        if n <= 30: return '16-30'
        return '>30'
    BINS = ['≤5','6-15','16-30','>30']

    # Cells to pool: HPO-input datasets only (pp-store, rarebench), strong cells.
    # Use Gemini Flash (N=500) for LLM agents + offline/classical baselines.
    POOL = [
        ('phenopacket_store','llm_control','google_gemini-3-flash-preview-2025'),
        ('phenopacket_store','mdagents','google_gemini-3-flash-preview-2025'),
        ('phenopacket_store','medagents','google_gemini-3-flash-preview-2025'),
        ('phenopacket_store','lirical','lirical-2.4.0'),
        ('phenopacket_store','vc_rdagent','vc_rdagent-offline-v1'),
        ('rarebench','llm_control','google_gemini-3-flash-preview-2025'),
        ('rarebench','mdagents','google_gemini-3-flash-preview-2025'),
        ('rarebench','medagents','google_gemini-3-flash-preview-2025'),
        ('rarebench','deeprare','google_gemini-3-flash-preview-2025'),
        ('rarebench','lirical','lirical-2.4.0'),
        ('rarebench','vc_rdagent','vc_rdagent-offline-v1'),
    ]
    def fpath(ds, ag, bb):
        for p in glob.glob(f'data/round2/phase4a/predictions_{ds}_{ag}_{bb}*.jsonl'):
            return p
        return None

    # Per-cell, dedupe by case_id (ok preferred), accumulate per-bin hits.
    # Report per-bin pooled R@1 (variants) and per-cell breakdown.
    per_bin = defaultdict(lambda: {'n':0,'h':0})
    per_cell_bin = defaultdict(lambda: defaultdict(lambda: {'n':0,'h':0}))
    for ds, ag, bb in POOL:
        p = fpath(ds, ag, bb)
        if not p: continue
        best = {}
        for line in open(p):
            try: r = json.loads(line)
            except: continue
            cid = r.get('case_id')
            if cid is None: continue
            prev = best.get(cid)
            if prev is None or (r.get('status')=='ok' and prev.get('status')!='ok'):
                best[cid] = r
            elif prev.get('status')!='ok':
                best[cid] = r
        for r in best.values():
            if r.get('status')!='ok': continue
            cid = r['case_id']; g = case_gold.get(cid)
            if not g or cid not in case_nhpo: continue
            b = bin_of(case_nhpo[cid])
            preds = r.get('ranked_predictions', [])
            variants = r.get('extra',{}).get('ranked_predictions_variants') or []
            hit = (variants and gold_hit_with_variants(variants[0], g)) or \
                  (preds and gold_hit_with_crossmap(preds[0], g))
            per_bin[b]['n'] += 1; per_bin[b]['h'] += 1 if hit else 0
            cellkey = f"{ds}|{ag}"
            per_cell_bin[cellkey][b]['n'] += 1
            per_cell_bin[cellkey][b]['h'] += 1 if hit else 0

    md = ["# H8 — Phenotype Density vs R@1 (inverted-U test)", "",
          "Bins = # gold HPO terms. HPO-input datasets (PP-Store + RareBench).",
          "Pooled over Gemini-Flash LLM cells + offline/classical baselines.", "",
          "## Pooled R@1 by HPO-term bin", "",
          "| Bin (#HPO) | n cases | R@1 |", "|---|---|---|"]
    r1_by_bin = {}
    for b in BINS:
        s = per_bin[b]
        r1 = s['h']/s['n'] if s['n'] else None
        r1_by_bin[b] = r1
        md.append(f"| {b} | {s['n']} | {('%.3f'%r1) if r1 is not None else '—'} |")
    md += ["", "## Inverted-U check", ""]
    vals = [(b, r1_by_bin[b]) for b in BINS if r1_by_bin.get(b) is not None]
    if len(vals) >= 3:
        peak_i = max(range(len(vals)), key=lambda i: vals[i][1])
        shape = ("monotonic-decreasing" if peak_i == 0 else
                 "monotonic-increasing" if peak_i == len(vals)-1 else
                 "inverted-U (interior peak)")
        md.append(f"Peak at bin **{vals[peak_i][0]}** (R@1={vals[peak_i][1]:.3f}). Shape: **{shape}**.")
        md.append("")
        md.append("H8 predicts inverted-U (interior peak). " +
                  ("**Supported.**" if 'inverted-U' in shape else
                   "**Not supported** — see per-cell breakdown for heterogeneity."))
    md += ["", "## Per-cell breakdown (R@1 by bin)", "",
           "| Cell | ≤5 | 6-15 | 16-30 | >30 |", "|---|---|---|---|---|"]
    for cell in sorted(per_cell_bin):
        row = [f"| `{cell}`"]
        for b in BINS:
            s = per_cell_bin[cell][b]
            row.append(f"{s['h']}/{s['n']}={s['h']/s['n']:.2f}" if s['n'] else "—")
        md.append(" | ".join(row) + " |")
    Path('data/round2/ablations').mkdir(parents=True, exist_ok=True)
    Path('data/round2/ablations/H8_phenotype_density.md').write_text("\n".join(md))
    print("Wrote H8_phenotype_density.md")
    print("\n".join(md[:20]))

if __name__ == "__main__":
    main()

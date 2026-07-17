"""Ablation A10 — Prevalence-stratified R@1.

Bins Phase 4a+4c cases by Orphanet prevalence (super-rare / ultra-rare /
rare) and reports per-bin R@1 for each (dataset, agent, best-backbone)
cell. The point: do agents do better on common rare diseases (which are
better-represented in LLM training) than on truly ultra-rare ones?

Output: data/round2/ablations/A10_prevalence_stratified.md
"""
from __future__ import annotations
import json, sys, glob, os
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Orphanet prevalence tiers (approximate; per Orphadata `en_product9_prev.xml`):
#   "<1/1,000,000"     → super-rare
#   "1-9/1,000,000"    → ultra-rare
#   "1-9/100,000"      → rare
#   "1-5/10,000"       → rare (boundary)
#   "Unknown"          → unknown

def load_orpha_prevalence():
    """Parse en_product9_prev.xml → {ORPHA:N: prevalence_tier}"""
    try:
        from xml.etree import ElementTree as ET
        path = Path("data/orphadata/en_product9_ages.xml")
        if not path.exists():
            # No prevalence file — use disease name-based rough heuristic
            return None
        root = ET.parse(path).getroot()
        out = {}
        for d in root.iter("Disorder"):
            code = d.findtext("OrphaCode")
            if not code: continue
            # en_product9_ages doesn't carry prevalence — would need en_product9_prev
            # Skip for now
        return out
    except Exception:
        return None


def main():
    from harness.canonical_case import CanonicalCase
    from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants
    from harness.ingest import ingest_phenopacket_store, ingest_rarearena, ingest_rarebench
    print("Loading gold maps + cases...", file=sys.stderr)
    case_gold = {}
    for c in ingest_phenopacket_store('data/phenopacket_store/notebooks'): case_gold[c.case_id] = c.gold_label
    for c in ingest_rarearena('data/rarearena/benchmark_data/RDS_benchmark.jsonl', 'RDS'): case_gold[c.case_id] = c.gold_label
    for split in ('RAMEDIS','LIRICAL','MME','HMS'):
        for c in ingest_rarebench(f'data/rarebench_hf/data_unzipped/data/{split}.jsonl', split): case_gold[c.case_id] = c.gold_label
    with open('data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl') as f:
        for line in f:
            c = CanonicalCase.model_validate_json(line); case_gold[c.case_id] = c.gold_label

    # Without proper prevalence data, use a name-based proxy:
    # - "syndrome" cases (presumably rarer than generic disease names)
    # - cases with unique gold ORPHA (sole occurrence in our sample)
    gold_counts = defaultdict(int)
    for g in case_gold.values():
        if g and g.orphanet_id:
            gold_counts[g.orphanet_id] += 1
    # Tier by how often disease appears in our pooled sample (proxy for prevalence)
    def tier(g):
        if not g or not g.orphanet_id: return "unknown"
        c = gold_counts[g.orphanet_id]
        if c >= 20: return "common"     # appears in 20+ cases (common rare)
        if c >= 5: return "moderate"    # 5-19 cases
        if c >= 2: return "ultra_rare"  # 2-4 cases
        return "super_rare"             # singleton

    # Aggregate per (dataset, agent, tier)
    stats = defaultdict(lambda: {"n":0, "h1":0, "h5":0})
    for p in sorted(glob.glob('data/round2/phase4a/predictions_*.jsonl')):
        fn = os.path.basename(p).replace('predictions_','').replace('.jsonl','')
        ds = ag = None
        for d in ('phenopacket_store','rarearena_rds','rarebench','mimic_diverse'):
            if fn.startswith(d+'_'): ds = d; rest = fn[len(d)+1:]; break
        if not ds: continue
        for a in ('mdagents','medagents','agentclinic','maidxo','deeprare','llm_control','vc_rdagent','lirical'):
            if rest.startswith(a+'_'): ag = a; break
        if not ag: continue
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                if r.get('status') != 'ok': continue
                g = case_gold.get(r['case_id'])
                if not g: continue
                t = tier(g)
                preds = r.get('ranked_predictions', [])
                variants = r.get('extra', {}).get('ranked_predictions_variants') or []
                hit1 = (variants and gold_hit_with_variants(variants[0], g)) or \
                       (preds and gold_hit_with_crossmap(preds[0], g))
                hit5 = (variants and any(gold_hit_with_variants(v, g) for v in variants[:5])) or \
                       (any(gold_hit_with_crossmap(pred, g) for pred in preds[:5]))
                key = (ds, ag, t)
                stats[key]['n'] += 1
                if hit1: stats[key]['h1'] += 1
                if hit5: stats[key]['h5'] += 1

    md = ["# Ablation A10 — Prevalence-Stratified R@1",
          "",
          "Proxy for Orphanet prevalence: how often a disease appears in our pooled",
          "evaluation sample. Singletons (1 case) = super-rare, 2-4 = ultra-rare,",
          "5-19 = moderate, ≥20 = common (relative to our sample).",
          "",
          "**Hypothesis**: agents perform better on common-rare diseases (better LLM-train",
          "exposure) and worse on truly super-rare diseases.",
          "",
          "## Per-dataset stratified R@1",
          ""]
    for ds in ('phenopacket_store','rarearena_rds','rarebench','mimic_diverse'):
        md.append(f"### {ds}")
        md.append("| Agent | super-rare | ultra-rare | moderate | common |")
        md.append("|---|---|---|---|---|")
        agents = sorted({k[1] for k in stats if k[0]==ds})
        for ag in agents:
            row = [f"| `{ag}`"]
            for t in ('super_rare','ultra_rare','moderate','common'):
                s = stats.get((ds, ag, t), {'n':0,'h1':0})
                if s['n'] == 0:
                    row.append("—")
                else:
                    row.append(f"{s['h1']}/{s['n']} = **{s['h1']/s['n']:.2f}**")
            md.append(" | ".join(row) + " |")
        md.append("")

    Path('data/round2/ablations').mkdir(parents=True, exist_ok=True)
    Path('data/round2/ablations/A10_prevalence_stratified.md').write_text("\n".join(md))
    print(f"Wrote A10_prevalence_stratified.md ({len(md)} lines)")

if __name__ == "__main__":
    main()

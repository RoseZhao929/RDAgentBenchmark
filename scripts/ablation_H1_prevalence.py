"""H1 — Prevalence stratification (REAL Orphanet prevalence, not sample proxy).

Pre-registered (plan.md): R@1 declines monotonically across prevalence tiers
(common-rare → super-rare). Anchored on real Orphadata `en_product9_prev.xml`.
Confirmatory expectation: LLM agents do better on commoner rare diseases
(training exposure); the inverse for prior-driven classical agents would refute
the universal form.

Tier (rarest→commonest), from PrevalenceClass (point-prevalence preferred):
  super_rare  = <1/1,000,000
  ultra_rare  = 1-9/1,000,000
  moderate    = 1-9/100,000
  common_rare = 1-5/10,000, 6-9/10,000, >1/1000

Output: data/round2/ablations/H1_prevalence_real.md
"""
from __future__ import annotations
import json, glob, sys
from pathlib import Path
from collections import defaultdict
from xml.etree import ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CLASS_TIER = {
    '<1 / 1 000 000': 'super_rare',
    '1-9 / 1 000 000': 'ultra_rare',
    '1-9 / 100 000': 'moderate',
    '1-5 / 10 000': 'common_rare',
    '6-9 / 10 000': 'common_rare',
    '>1 / 1000': 'common_rare',
}
TIER_ORDER = ['common_rare', 'moderate', 'ultra_rare', 'super_rare']  # commonest→rarest
TIER_RANK = {t: -i for i, t in enumerate(TIER_ORDER)}  # for severity sort

def load_prevalence():
    """ORPHA:N -> tier. Prefer Point prevalence; among entries pick rarest class
    (conservative: a disease counts as rare as its rarest validated estimate)."""
    root = ET.parse('data/orphadata/en_product9_prev.xml').getroot()
    out = {}
    sev = {t: i for i, t in enumerate(TIER_ORDER)}  # 0 common .. 3 super
    for d in root.iter('Disorder'):
        code = d.findtext('OrphaCode')
        if not code: continue
        point_tiers, any_tiers = [], []
        for prev in d.iter('Prevalence'):
            pc = prev.find('PrevalenceClass')
            nm = pc.findtext('Name') if pc is not None else None
            t = CLASS_TIER.get(nm)
            if not t: continue
            pt = prev.find('PrevalenceType')
            ptn = pt.findtext('Name') if pt is not None else None
            (point_tiers if ptn == 'Point prevalence' else any_tiers).append(t)
        pool = point_tiers or any_tiers
        if pool:
            # rarest = max severity
            out[f'ORPHA:{code}'] = max(pool, key=lambda t: sev[t])
    return out

def main():
    from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants, omim_to_orpha
    from harness.canonical_case import CanonicalCase
    from harness.ingest import ingest_phenopacket_store, ingest_rarearena, ingest_rarebench
    prev = load_prevalence()
    print(f'prevalence tiers loaded for {len(prev)} ORPHA codes', file=sys.stderr)

    case_gold = {}
    for c in ingest_phenopacket_store('data/phenopacket_store/notebooks'): case_gold[c.case_id]=c.gold_label
    for c in ingest_rarearena('data/rarearena/benchmark_data/RDS_benchmark.jsonl','RDS'): case_gold[c.case_id]=c.gold_label
    for split in ('RAMEDIS','LIRICAL','MME','HMS'):
        for c in ingest_rarebench(f'data/rarebench_hf/data_unzipped/data/{split}.jsonl',split): case_gold[c.case_id]=c.gold_label
    with open('data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl') as f:
        for line in f:
            c=CanonicalCase.model_validate_json(line); case_gold[c.case_id]=c.gold_label

    def tier_of(g):
        if not g: return None
        # try gold orphanet_id, else OMIM->ORPHA crossmap
        cands = []
        if g.orphanet_id: cands.append(g.orphanet_id)
        if g.omim_id: cands += omim_to_orpha(g.omim_id)
        for oid in cands:
            if oid in prev: return prev[oid]
        return None

    # LLM cells (Gemini Flash N=500) vs classical (lirical/vc_rdagent offline)
    LLM = [('phenopacket_store','llm_control'),('phenopacket_store','mdagents'),('phenopacket_store','medagents'),
           ('rarearena_rds','llm_control'),('rarearena_rds','mdagents'),('rarearena_rds','medagents'),
           ('rarebench','llm_control'),('rarebench','mdagents'),('rarebench','medagents')]
    CLASSICAL = [('phenopacket_store','lirical'),('phenopacket_store','vc_rdagent'),
                 ('rarebench','lirical'),('rarebench','vc_rdagent')]
    def cell_files(cells, bb_filter):
        for ds, ag in cells:
            for p in glob.glob(f'data/round2/phase4a/predictions_{ds}_{ag}_*.jsonl'):
                if bb_filter and bb_filter not in p: continue
                yield p

    def accumulate(files):
        per = defaultdict(lambda: {'n':0,'h':0})
        for p in files:
            best={}
            for line in open(p):
                try: r=json.loads(line)
                except: continue
                cid=r.get('case_id')
                if cid is None: continue
                pr=best.get(cid)
                if pr is None or (r.get('status')=='ok' and pr.get('status')!='ok'): best[cid]=r
                elif pr.get('status')!='ok': best[cid]=r
            for r in best.values():
                if r.get('status')!='ok': continue
                g=case_gold.get(r['case_id']); t=tier_of(g)
                if not t: continue
                preds=r.get('ranked_predictions',[]); variants=r.get('extra',{}).get('ranked_predictions_variants') or []
                hit=(variants and gold_hit_with_variants(variants[0],g)) or (preds and gold_hit_with_crossmap(preds[0],g))
                per[t]['n']+=1; per[t]['h']+= 1 if hit else 0
        return per

    llm = accumulate(cell_files(LLM, 'google_gemini-3-flash-preview'))
    cla = accumulate(cell_files(CLASSICAL, None))

    def tbl(per):
        rows=[]
        for t in TIER_ORDER:
            s=per[t]; r1=s['h']/s['n'] if s['n'] else None
            rows.append((t, s['n'], r1))
        return rows
    def trend(rows):
        vals=[r1 for _,n,r1 in rows if r1 is not None]
        if len(vals)<3: return 'insufficient'
        # commonest→rarest order; H1 predicts decreasing
        dec=all(vals[i]>=vals[i+1] for i in range(len(vals)-1))
        inc=all(vals[i]<=vals[i+1] for i in range(len(vals)-1))
        return 'monotonic-decreasing (H1 supported)' if dec else \
               'monotonic-increasing (H1 inverse)' if inc else 'non-monotonic'

    md=["# H1 — Prevalence-Stratified R@1 (REAL Orphanet prevalence)","",
        f"Prevalence from `en_product9_prev.xml` ({len(prev)} ORPHA codes; point-prevalence preferred, rarest class per disease).",
        "Tier order = commonest→rarest. H1 predicts R@1 *decreases* toward rarer.","",
        "## LLM agents (Gemini Flash, N=500 cells pooled)","",
        "| Tier (commonest→rarest) | n | R@1 |","|---|---|---|"]
    for t,n,r1 in tbl(llm): md.append(f"| {t} | {n} | {('%.3f'%r1) if r1 is not None else '—'} |")
    md.append(f"\n**Trend**: {trend(tbl(llm))}")
    md+=["","## Classical/offline (LIRICAL + VC-RDAgent)","",
         "| Tier (commonest→rarest) | n | R@1 |","|---|---|---|"]
    for t,n,r1 in tbl(cla): md.append(f"| {t} | {n} | {('%.3f'%r1) if r1 is not None else '—'} |")
    md.append(f"\n**Trend**: {trend(tbl(cla))}")
    md+=["","## Interpretation","",
         "H1 (universal monotonic decline) is tested per agent-class. A decline for",
         "LLMs + an *inverse* for prior-driven classical agents would mean H1 holds",
         "for parametric models (training-frequency effect) but not for Bayesian",
         "phenotype-matching — a backbone-vs-method distinction worth reporting."]
    Path('data/round2/ablations/H1_prevalence_real.md').write_text("\n".join(md))
    print("Wrote H1_prevalence_real.md")
    print("\n".join(md))

if __name__=='__main__':
    main()

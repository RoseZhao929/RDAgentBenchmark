"""补1 — temporal holdout difficulty-matching + contamination-clean recompute.

For pre (pmc_precutoff, 220) vs post (pmc_oa_holdout, 198), on the shared
Gemini-Flash backbone across the 4 shared systems:

  1. Build per-case difficulty features:
       - phenotype_count: # phenotype phrases in the "Clinical phenotypes:" vignette
       - prevalence_tier:  from Orphadata en_product9_prev (gold ORPHA -> prevalence class)
       - disease_category: top-level Orphanet linearisation group (vc_rdagent categorization csv)
  2. Report pre/post balance on these features.
  3. Coarse exact-match on (phenotype_count bucket x prevalence_tier): keep only
     buckets present on BOTH sides, recompute matched pre/post pooled R@1.
  4. Contamination-clean: drop the RareArena-overlapping PMCIDs (from
     _contamination_scan.json) and recompute pre/post pooled R@1.

Pure offline. Attempted-denominator, variant-aware, same as the frozen audit.
"""
from __future__ import annotations
import sys, json, re, os, math
from pathlib import Path
from collections import defaultdict, Counter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO)); os.chdir(REPO)
import recompute_engine as eng  # noqa: E402  (applies orphadata + fuzzy patches)
from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants  # noqa: E402
from scipy import stats  # noqa: E402

OUT = REPO / 'audit_frozen'
GOLD, _ = eng.load_gold()

SHARED_SYS = ('agentclinic', 'llm_control', 'mdagents', 'medagents')
BB = 'gemini-3-flash-preview'

# ---------------------------------------------------------------- difficulty feats
def prevalence_map():
    """gold ORPHA:NNNN -> prevalence class string, from en_product9_prev.xml."""
    import xml.etree.ElementTree as ET
    root = ET.parse('data/orphadata/en_product9_prev.xml').getroot()
    out = {}
    for dis in root.iter('Disorder'):
        code = dis.findtext('OrphaCode')
        if not code:
            continue
        # pick the "Point prevalence" / most-informative class if present
        best = None
        for prev in dis.iter('Prevalence'):
            ptype = (prev.findtext('PrevalenceType/Name') or '')
            cls = (prev.findtext('PrevalenceClass/Name') or '').strip()
            valmoy = prev.findtext('ValMoy')
            if cls:
                if best is None or 'Point' in ptype:
                    best = cls
        if best:
            out[f'ORPHA:{code}'] = best
    return out

def category_map():
    """gold ORPHA -> top Orphanet category, from vc_rdagent categorization csv."""
    import csv
    path = 'agents/vc_rdagent/orphanet_annotations/categorization_of_orphanet_diseases.csv'
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames or []
        orpha_col = next((c for c in cols if 'orpha' in c.lower()), None)
        cat_col = next((c for c in cols if 'categ' in c.lower() or 'group' in c.lower() or 'class' in c.lower()), None)
        if not orpha_col:
            return out
        for row in rd:
            oc = str(row.get(orpha_col, '')).strip()
            m = re.search(r'(\d+)', oc)
            if m:
                out[f'ORPHA:{m.group(1)}'] = (row.get(cat_col) or 'NA') if cat_col else 'NA'
    return out

def pheno_count(vignette):
    """# phenotype phrases in a 'Clinical phenotypes: a; b; c.' vignette."""
    if not vignette:
        return 0
    v = vignette
    v = re.sub(r'(?i)^clinical phenotypes:\s*', '', v.strip())
    parts = [p.strip() for p in re.split(r'[;.]', v) if p.strip()]
    return len(parts)

def pheno_bucket(n):
    return '<=5' if n <= 5 else '6-15' if n <= 15 else '16-30' if n <= 30 else '>30'

# ---------------------------------------------------------------- per-case hits
def holdout_case_features(split_path):
    """case_id -> dict(orpha, pheno_n, pheno_bkt)."""
    feats = {}
    for line in open(split_path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        orpha = r['gold_label'].get('orphanet_id')
        n = pheno_count(r.get('free_text_vignette'))
        feats[r['case_id']] = {'orpha': orpha, 'pheno_n': n, 'pheno_bkt': pheno_bucket(n)}
    return feats

def cell_case_hits(dataset, system, bb=BB):
    """case_id -> 0/1 variant-aware hit (attempted; failure -> 0)."""
    import glob
    out = {}
    for p in glob.glob(f'data/round2/phase4a/predictions_{dataset}_{system}_*.jsonl'):
        if bb not in os.path.basename(p):
            continue
        best = eng.dedupe_cases(p)
        for cid, r in best.items():
            if not eng.is_success(r):
                out[cid] = 0
                continue
            _, g = GOLD.get(cid, (None, None))
            if not g:
                out[cid] = 0
                continue
            variants = (r.get('extra') or {}).get('ranked_predictions_variants') or []
            preds = r.get('ranked_predictions', [])
            if variants:
                out[cid] = 1 if gold_hit_with_variants(variants[0], g) else 0
            else:
                out[cid] = 1 if (preds and gold_hit_with_crossmap(preds[0], g)) else 0
    return out

def two_prop_z(h1, n1, h2, n2):
    if not n1 or not n2:
        return None, None
    p1, p2 = h1 / n1, h2 / n2
    pp = (h1 + h2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p2 - p1) / se
    return round(z, 3), float(2 * stats.norm.sf(abs(z)))

def pooled(cases_by_split_sys, keep):
    """keep: set of case_ids allowed. Return (hits, n) pooled over shared systems."""
    h = n = 0
    for sysname in SHARED_SYS:
        for cid, hit in cases_by_split_sys[sysname].items():
            if cid in keep:
                h += hit; n += 1
    return h, n

# ---------------------------------------------------------------- run
def main():
    prev = prevalence_map()
    cat = category_map()
    feat_pre = holdout_case_features('data/pmc_precutoff/holdout_gold_opus.jsonl')
    feat_post = holdout_case_features('data/pmc_oa_holdout/holdout_gold_opus.jsonl')
    for feats in (feat_pre, feat_post):
        for cid, d in feats.items():
            d['prev_tier'] = prev.get(d['orpha'], 'unknown')
            d['category'] = cat.get(d['orpha'], 'NA')

    hits_pre = {s: cell_case_hits('pmc_precutoff', s) for s in SHARED_SYS}
    hits_post = {s: cell_case_hits('pmc_oa_holdout', s) for s in SHARED_SYS}

    # contamination overlap set (PMCIDs overlapping RareArena)
    scan = json.loads((OUT / '_contamination_scan.json').read_text())
    def cont_caseids(split, feats):
        pmcs = set(scan['exact_id_overlap'][split]['pmcid_overlap_with_rarearena'])
        return {cid for cid in feats if re.match(r'pmc_?(\d+)', cid) and re.match(r'pmc_?(\d+)', cid).group(1) in pmcs}
    cont_pre = cont_caseids('pre_cutoff', feat_pre)
    cont_post = cont_caseids('post_cutoff', feat_post)

    all_pre = set(feat_pre); all_post = set(feat_post)

    def balance(feats, key):
        c = Counter(feats[cid][key] for cid in feats)
        return dict(c)

    report = {
        'backbone': BB, 'shared_systems': list(SHARED_SYS),
        'balance': {
            'pheno_bucket': {'pre': balance(feat_pre, 'pheno_bkt'), 'post': balance(feat_post, 'pheno_bkt')},
            'prev_tier': {'pre': balance(feat_pre, 'prev_tier'), 'post': balance(feat_post, 'prev_tier')},
        },
        'contamination': {
            'pre_overlap_cases': len(cont_pre), 'post_overlap_cases': len(cont_post),
            'pre_total': len(all_pre), 'post_total': len(all_post),
        },
        'recompute_variants': {},
    }

    # (a) raw all cases
    hp, np_ = pooled(hits_pre, all_pre); hq, nq = pooled(hits_post, all_post)
    z, p = two_prop_z(hp, np_, hq, nq)
    report['recompute_variants']['all_cases'] = {
        'pre_R@1': round(hp / np_, 4), 'post_R@1': round(hq / nq, 4),
        'delta_pp': round((hq / nq - hp / np_) * 100, 1), 'z': z, 'p': p,
        'pre_n': np_, 'post_n': nq}

    # (b) contamination-clean (drop RareArena-overlap cases)
    keep_pre = all_pre - cont_pre; keep_post = all_post - cont_post
    hp, np_ = pooled(hits_pre, keep_pre); hq, nq = pooled(hits_post, keep_post)
    z, p = two_prop_z(hp, np_, hq, nq)
    report['recompute_variants']['contamination_clean'] = {
        'pre_R@1': round(hp / np_, 4), 'post_R@1': round(hq / nq, 4),
        'delta_pp': round((hq / nq - hp / np_) * 100, 1), 'z': z, 'p': p,
        'pre_n': np_, 'post_n': nq,
        'note': 'dropped RareArena-overlapping PMCIDs from both splits'}

    # (c) difficulty-matched: coarse exact match on (pheno_bkt x prev_tier),
    #     keep only strata present on both sides; equalise by min count per stratum.
    def strata(feats):
        s = defaultdict(list)
        for cid, d in feats.items():
            s[(d['pheno_bkt'], d['prev_tier'])].append(cid)
        return s
    sp, sq = strata(feat_pre), strata(feat_post)
    matched_pre, matched_post = set(), set()
    for k in set(sp) & set(sq):
        m = min(len(sp[k]), len(sq[k]))
        matched_pre.update(sorted(sp[k])[:m])
        matched_post.update(sorted(sq[k])[:m])
    hp, np_ = pooled(hits_pre, matched_pre); hq, nq = pooled(hits_post, matched_post)
    z, p = two_prop_z(hp, np_, hq, nq)
    report['recompute_variants']['difficulty_matched'] = {
        'pre_R@1': round(hp / np_, 4) if np_ else None,
        'post_R@1': round(hq / nq, 4) if nq else None,
        'delta_pp': round((hq / nq - hp / np_) * 100, 1) if np_ and nq else None,
        'z': z, 'p': p, 'pre_n': np_, 'post_n': nq,
        'n_matched_strata': len(set(sp) & set(sq)),
        'match_keys': '(pheno_bucket x prevalence_tier), min-count per stratum'}

    (OUT / '_holdout_difficulty.json').write_text(json.dumps(report, indent=2, default=str))
    for name, v in report['recompute_variants'].items():
        print(f"[{name}] pre={v['pre_R@1']}(n={v['pre_n']}) post={v['post_R@1']}(n={v['post_n']}) "
              f"Δ={v['delta_pp']}pp p={v['p']}")
    print("balance pheno_bucket:", report['balance']['pheno_bucket'])
    print("contamination:", report['contamination'])

if __name__ == '__main__':
    main()

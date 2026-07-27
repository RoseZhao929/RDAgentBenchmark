"""Temporal-holdout FINAL frozen recompute (v2).

Rebuilds the temporal (pre/post-cutoff) test set as a *disjoint* set after
removing every case that overlaps ANY development layer by exact publication
identity, then recomputes per-system results (Holm-corrected) and a
pseudo-replication-free case-level macro summary.

NO paper text is modified. NO LLM is called. Uses only the frozen pre/post
prediction receipts already on disk.

Identity model (unified publication identity per case)
------------------------------------------------------
Available in the frozen data:
  - PMCID : holdout case_id `pmc_<PMCID>`; RareArena `_id` prefix `<PMCID>-n`.
  - PMID  : holdout via data/pmc_*/02_pmid_to_pmc.jsonl; Phenopacket case_id
            `PMID_<pmid>_...`.
  - source case ID : the dataset-native id.
NOT available anywhere in the frozen data:
  - DOI, normalized article title -> emitted as columns but NULL, with an
    explicit note. Intersection therefore rests on PMCID + PMID (both exact).

Development layers intersected (exact ID):
  - RareArena RDS      (PMCID)
  - Phenopacket Store  (PMID)
  - RareBench          (NO publication id in the shipped data -> CANNOT be
                        ID-intersected; reported as a coverage gap, not disjoint)
  - other PMC prompt/adapter dev cases: none present as case-report corpora in
    this checkout (agents/vc_rdagent/* are ontologies, not PMC cases).

Removal = union over all ID-overlapping dev sources (not just RareArena).
"""
from __future__ import annotations
import sys, os, json, re, csv, glob, math, hashlib, subprocess
from pathlib import Path
from collections import defaultdict, Counter

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'audit_frozen'))
os.chdir(REPO)

import recompute_engine as eng  # applies orphadata + fuzzy patches, verbatim matching
from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants
from harness.ingest import ingest_phenopacket_store, ingest_rarearena
import numpy as np
from scipy import stats

OUT = REPO / 'audit_frozen' / 'temporal_v2'
GOLD, _PROV = eng.load_gold()

SHARED_SYS = ('agentclinic', 'llm_control', 'mdagents', 'medagents')  # both-side, both-backbone check below
BB = 'gemini-3-flash-preview'  # only backbone with BOTH pre and post across all 4 systems
SEED = 42

FROZEN_COMMIT = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
GEN_TIME = subprocess.check_output(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ']).decode().strip()
DATA_VERSION = 'slim recompute set (MIMIC & weights stripped); frozen commit ' + FROZEN_COMMIT[:12]

# ------------------------------------------------------------------ identities
def norm_title(t):
    if not t:
        return ''
    return re.sub(r'[^a-z0-9]+', ' ', t.lower()).strip()

def pmcid_of_caseid(cid):
    m = re.match(r'pmc_?(\d+)', str(cid))
    return m.group(1) if m else None

def load_holdout_identity(split_dir):
    """case_id -> {pmcid, pmid, doi, title, source_case_id}."""
    gold_path = REPO / 'data' / split_dir / 'holdout_gold_opus.jsonl'
    map_path = REPO / 'data' / split_dir / '02_pmid_to_pmc.jsonl'
    pmc2pmid = {}
    if map_path.exists():
        for line in open(map_path):
            d = json.loads(line)
            pmc = str(d.get('pmc_id', '')).replace('PMC', '').strip()
            if pmc:
                pmc2pmid[pmc] = str(d.get('pmid', '')).strip()
    ids = {}
    for line in open(gold_path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        cid = r['case_id']
        pmcid = pmcid_of_caseid(cid)
        ids[cid] = {
            'pmcid': pmcid,
            'pmid': pmc2pmid.get(pmcid, ''),
            'doi': '',            # not present in frozen data
            'title': '',          # not present in frozen data
            'source_case_id': cid,
            'gold_orpha': (r.get('gold_label') or {}).get('orphanet_id'),
        }
    return ids

# ------------------------------------------------------------------ dev layers
def rarearena_index():
    """PMCID -> (source_case_id, gold_orpha)."""
    idx = {}
    for line in open('data/rarearena/benchmark_data/RDS_benchmark.jsonl'):
        r = json.loads(line)
        _id = str(r['_id'])
        pmc = _id.split('-')[0]
        oc = str(r.get('Orpha_id', '')).strip()
        orpha = f'ORPHA:{oc}' if oc and not oc.startswith('ORPHA') else oc
        # keep first occurrence per pmcid for reporting the dev case id
        idx.setdefault(pmc, (_id, orpha))
    return idx

def phenopacket_index():
    """PMID -> (source_case_id, gold_orpha_or_omim)."""
    idx = {}
    for c in ingest_phenopacket_store('data/phenopacket_store/notebooks'):
        m = re.match(r'PMID_(\d+)', c.case_id)
        if not m:
            continue
        pmid = m.group(1)
        gl = c.gold_label
        gold = gl.orphanet_id or gl.omim_id
        idx.setdefault(pmid, (c.case_id, gold))
    return idx

def orpha_agreement(a, b):
    """Compare two gold ids loosely (both may be ORPHA/OMIM strings)."""
    if not a or not b:
        return 'unknown'
    na = re.sub(r'\s+', '', str(a)).upper()
    nb = re.sub(r'\s+', '', str(b)).upper()
    return 'match' if na == nb else 'differ'

# ------------------------------------------------------------------ overlap
def build_overlap(split, split_dir, ra_idx, pp_idx):
    """Return (removals[list of dict], overlap_by_source dict, union set of case_ids)."""
    ids = load_holdout_identity(split_dir)
    removals = []
    by_source = defaultdict(set)   # source -> set(case_id)
    for cid, m in ids.items():
        hit_sources = []
        # RareArena via PMCID
        if m['pmcid'] and m['pmcid'] in ra_idx:
            dev_cid, dev_gold = ra_idx[m['pmcid']]
            removals.append({
                'split': split, 'case_id': cid, 'pmcid': m['pmcid'], 'pmid': m['pmid'],
                'doi': m['doi'], 'title': m['title'],
                'overlapping_dev_source': 'rarearena_rds', 'dev_case_id': dev_cid,
                'match_key': 'PMCID', 'match_value': m['pmcid'],
                'gold_orpha_holdout': m['gold_orpha'], 'gold_orpha_dev': dev_gold,
                'gold_orpha_agreement': orpha_agreement(m['gold_orpha'], dev_gold),
                'removal_reason': 'exact PMCID match to RareArena development case',
            })
            by_source['rarearena_rds'].add(cid)
            hit_sources.append('rarearena_rds')
        # Phenopacket via PMID
        if m['pmid'] and m['pmid'] in pp_idx:
            dev_cid, dev_gold = pp_idx[m['pmid']]
            removals.append({
                'split': split, 'case_id': cid, 'pmcid': m['pmcid'], 'pmid': m['pmid'],
                'doi': m['doi'], 'title': m['title'],
                'overlapping_dev_source': 'phenopacket_store', 'dev_case_id': dev_cid,
                'match_key': 'PMID', 'match_value': m['pmid'],
                'gold_orpha_holdout': m['gold_orpha'], 'gold_orpha_dev': dev_gold,
                'gold_orpha_agreement': orpha_agreement(m['gold_orpha'], dev_gold),
                'removal_reason': 'exact PMID match to Phenopacket-Store development case',
            })
            by_source['phenopacket_store'].add(cid)
            hit_sources.append('phenopacket_store')
    union = set().union(*by_source.values()) if by_source else set()
    return ids, removals, by_source, union

# ------------------------------------------------------------------ hits
def cell_case_hits(dataset, system, bb=BB):
    """case_id -> 0/1 variant-aware hit (attempted denom; failure -> 0).
    Also returns strict hits + a status breakdown for the manifest."""
    out_v, out_s, status = {}, {}, {}
    for p in glob.glob(f'data/round2/phase4a/predictions_{dataset}_{system}_*.jsonl'):
        if bb not in os.path.basename(p):
            continue
        best = eng.dedupe_cases(p)
        for cid, r in best.items():
            st = r.get('status', '?')
            if not eng.is_success(r):
                out_v[cid] = 0; out_s[cid] = 0
                status[cid] = ('empty_ok' if st == 'ok' else st)
                continue
            status[cid] = 'ok'
            _, g = GOLD.get(cid, (None, None))
            if not g:
                out_v[cid] = 0; out_s[cid] = 0
                status[cid] = 'no_gold'
                continue
            preds = r.get('ranked_predictions', [])
            variants = (r.get('extra') or {}).get('ranked_predictions_variants') or []
            out_s[cid] = 1 if (preds and gold_hit_with_crossmap(preds[0], g)) else 0
            if variants:
                out_v[cid] = 1 if gold_hit_with_variants(variants[0], g) else 0
            else:
                out_v[cid] = out_s[cid]
    return out_v, out_s, status

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

def boot_ci_rate(hits, n, n_boot=5000, seed=SEED):
    if not n:
        return (0.0, 0.0)
    p = hits / n
    rng = np.random.default_rng(seed)
    rates = rng.binomial(n, p, size=n_boot) / n
    return (round(float(np.percentile(rates, 2.5)), 4),
            round(float(np.percentile(rates, 97.5)), 4))

def holm(pvals):
    """Return dict idx->adjusted p (Holm-Bonferroni), preserving order."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    adj = [None] * m
    running = 0.0
    for rank, i in enumerate(idx):
        a = (m - rank) * pvals[i]
        running = max(running, a)
        adj[i] = min(1.0, running)
    return adj

# ------------------------------------------------------------------ difficulty
def pheno_count(vig):
    if not vig:
        return 0
    v = re.sub(r'(?i)^clinical phenotypes:\s*', '', vig.strip())
    return len([p for p in re.split(r'[;.]', v) if p.strip()])

def pheno_bucket(n):
    return '<=5' if n <= 5 else '6-15' if n <= 15 else '16-30' if n <= 30 else '>30'

def prevalence_map():
    import xml.etree.ElementTree as ET
    root = ET.parse('data/orphadata/en_product9_prev.xml').getroot()
    out = {}
    for dis in root.iter('Disorder'):
        code = dis.findtext('OrphaCode')
        if not code:
            continue
        best = None
        for prev in dis.iter('Prevalence'):
            ptype = prev.findtext('PrevalenceType/Name') or ''
            cls = (prev.findtext('PrevalenceClass/Name') or '').strip()
            if cls and (best is None or 'Point' in ptype):
                best = cls
        if best:
            out[f'ORPHA:{code}'] = best
    return out

def holdout_features(split_dir, prev):
    feats = {}
    for line in open(REPO / 'data' / split_dir / 'holdout_gold_opus.jsonl'):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        orpha = (r.get('gold_label') or {}).get('orphanet_id')
        n = pheno_count(r.get('free_text_vignette'))
        feats[r['case_id']] = {
            'orpha': orpha, 'pheno_n': n, 'pheno_bkt': pheno_bucket(n),
            'prev_tier': prev.get(orpha, 'unknown'),
        }
    return feats


# ================================================================== MAIN
def main():
    ra_idx = rarearena_index()
    pp_idx = phenopacket_index()
    prev = prevalence_map()

    SPLITS = {'pre_cutoff': 'pmc_precutoff', 'post_cutoff': 'pmc_oa_holdout'}
    DATASET = {'pre_cutoff': 'pmc_precutoff', 'post_cutoff': 'pmc_oa_holdout'}

    # -------- 1. overlap / removals ------------------------------------------
    all_removals = []
    overlap_meta = {}
    clean_ids = {}
    full_ids = {}
    for split, sdir in SPLITS.items():
        ids, removals, by_source, union = build_overlap(split, sdir, ra_idx, pp_idx)
        all_removals.extend(removals)
        full_ids[split] = set(ids)
        clean_ids[split] = set(ids) - union
        overlap_meta[split] = {
            'n_total': len(ids),
            'overlap_by_source': {s: len(v) for s, v in by_source.items()},
            'n_overlap_union': len(union),
            'n_clean': len(ids) - len(union),
            'overlap_case_ids_union': sorted(union),
        }

    # write temporal_overlap_audit.csv (one row per removed case-source pair)
    ovl_fields = ['split', 'case_id', 'pmcid', 'pmid', 'doi', 'title',
                  'overlapping_dev_source', 'dev_case_id', 'match_key', 'match_value',
                  'gold_orpha_holdout', 'gold_orpha_dev', 'gold_orpha_agreement',
                  'removal_reason']
    with open(OUT / 'temporal_overlap_audit.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ovl_fields)
        w.writeheader()
        w.writerows(sorted(all_removals, key=lambda r: (r['split'], r['case_id'], r['overlapping_dev_source'])))

    # -------- 2. frozen clean case lists -------------------------------------
    header = (f"# data_version: {DATA_VERSION}\n"
              f"# generator: audit_frozen/temporal_v2/build_temporal_v2.py\n"
              f"# commit: {FROZEN_COMMIT}\n"
              f"# generated_at_utc: {GEN_TIME}\n")
    for split, fname in (('pre_cutoff', 'temporal_pre_clean_case_ids.txt'),
                         ('post_cutoff', 'temporal_post_clean_case_ids.txt')):
        with open(OUT / fname, 'w') as f:
            f.write(header)
            for cid in sorted(clean_ids[split]):
                f.write(cid + '\n')

    # -------- 3. per-system results (both-side, both-backbone) ---------------
    # compute hits for BOTH backbones to document which are truly paired both-side
    per_system_rows = []
    hits_pre_bb = {}   # system -> (v,s,status)
    hits_post_bb = {}
    for sysname in SHARED_SYS:
        hits_pre_bb[sysname] = cell_case_hits(DATASET['pre_cutoff'], sysname, BB)
        hits_post_bb[sysname] = cell_case_hits(DATASET['post_cutoff'], sysname, BB)

    def system_stat(sysname, keep_pre, keep_post):
        v_pre, s_pre, st_pre = hits_pre_bb[sysname]
        v_post, s_post, st_post = hits_post_bb[sysname]
        pre_ids = [c for c in v_pre if c in keep_pre]
        post_ids = [c for c in v_post if c in keep_post]
        def agg(ids, v, s, st):
            n_att = len(ids)
            n_succ = sum(1 for c in ids if st.get(c) == 'ok')
            fails = Counter(st.get(c) for c in ids if st.get(c) != 'ok')
            h1v = sum(v[c] for c in ids)
            h1s = sum(s[c] for c in ids)
            return n_att, n_succ, dict(fails), h1v, h1s
        na1, ns1, f1, hv1, hs1 = agg(pre_ids, v_pre, s_pre, st_pre)
        na2, ns2, f2, hv2, hs2 = agg(post_ids, v_post, s_post, st_post)
        z, p = two_prop_z(hv1, na1, hv2, na2)
        return {
            'system': sysname, 'backbone': BB,
            'n_pre_attempted': na1, 'n_post_attempted': na2,
            'n_pre_successful': ns1, 'n_post_successful': ns2,
            'pre_failures_by_type': json.dumps(f1), 'post_failures_by_type': json.dumps(f2),
            'pre_top1_correct_variant': hv1, 'post_top1_correct_variant': hv2,
            'pre_R@1_variant': round(hv1 / na1, 4) if na1 else None,
            'post_R@1_variant': round(hv2 / na2, 4) if na2 else None,
            'pre_R@1_strict': round(hs1 / na1, 4) if na1 else None,
            'post_R@1_strict': round(hs2 / na2, 4) if na2 else None,
            'pre_95CI': str(list(boot_ci_rate(hv1, na1))),
            'post_95CI': str(list(boot_ci_rate(hv2, na2))),
            'delta_R@1_pp': round((hv2 / na2 - hv1 / na1) * 100, 1) if na1 and na2 else None,
            'two_prop_z': z, 'p_raw': p,
        }

    for sysname in SHARED_SYS:
        per_system_rows.append(system_stat(sysname, clean_ids['pre_cutoff'], clean_ids['post_cutoff']))
    # Holm across the 4 systems
    praw = [r['p_raw'] for r in per_system_rows]
    padj = holm(praw)
    for r, pa in zip(per_system_rows, padj):
        r['p_holm'] = pa

    ps_fields = list(per_system_rows[0].keys())
    with open(OUT / 'temporal_holdout_clean_results.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ps_fields)
        w.writeheader()
        w.writerows(per_system_rows)

    # -------- clean manifest (per split x system, richer than results) -------
    man_rows = []
    for split in ('pre_cutoff', 'post_cutoff'):
        keep = clean_ids[split]
        hb = hits_pre_bb if split == 'pre_cutoff' else hits_post_bb
        for sysname in SHARED_SYS:
            v, s, st = hb[sysname]
            ids = [c for c in v if c in keep]
            n_att = len(ids)
            n_succ = sum(1 for c in ids if st.get(c) == 'ok')
            fails = Counter(st.get(c) for c in ids if st.get(c) != 'ok')
            hv = sum(v[c] for c in ids); hs = sum(s[c] for c in ids)
            man_rows.append({
                'split': split, 'system': sysname, 'backbone': BB,
                'n_full_before_dedup_removal': overlap_meta[split]['n_total'],
                'n_overlap_removed_union': overlap_meta[split]['n_overlap_union'],
                'n_clean_cases': overlap_meta[split]['n_clean'],
                'n_attempted': n_att, 'n_successful': n_succ,
                'fail_timeout': fails.get('timeout', 0), 'fail_parser': fails.get('parser_error', 0),
                'fail_agent': fails.get('agent_error', 0), 'fail_empty_ok': fails.get('empty_ok', 0),
                'no_gold': fails.get('no_gold', 0),
                'top1_correct_strict': hs, 'top1_correct_variant': hv,
                'R@1_strict': round(hs / n_att, 4) if n_att else None,
                'R@1_variant_aware': round(hv / n_att, 4) if n_att else None,
                'bootstrap_95CI_variant': str(list(boot_ci_rate(hv, n_att))),
            })
    with open(OUT / 'temporal_holdout_clean_manifest.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(man_rows[0].keys()))
        w.writeheader(); w.writerows(man_rows)

    # -------- 4. case-level macro (pseudo-replication-free) ------------------
    def case_macro(keep_pre, keep_post):
        """Each case = mean correctness over the 4 systems. Sampling unit = case.
        Cluster bootstrap: resample cases (with their 4-system vector) together."""
        def per_case_mean(split_hits, keep):
            # case_id -> list of variant hits across systems (only cases with all
            # 4 systems present get a full 4-vector; use whatever systems have it)
            acc = defaultdict(list)
            for sysname in SHARED_SYS:
                v = split_hits[sysname][0]
                for cid, hit in v.items():
                    if cid in keep:
                        acc[cid].append(hit)
            return {cid: sum(x) / len(x) for cid, x in acc.items() if x}
        pre_means = per_case_mean(hits_pre_bb, keep_pre)
        post_means = per_case_mean(hits_post_bb, keep_post)
        pre_v = np.array(list(pre_means.values()), dtype=float)
        post_v = np.array(list(post_means.values()), dtype=float)
        delta = post_v.mean() - pre_v.mean()
        rng = np.random.default_rng(SEED)
        boots = []
        for _ in range(10000):
            bp = rng.choice(pre_v, size=len(pre_v), replace=True).mean()
            bq = rng.choice(post_v, size=len(post_v), replace=True).mean()
            boots.append(bq - bp)
        boots = np.array(boots)
        ci = (round(float(np.percentile(boots, 2.5)), 4),
              round(float(np.percentile(boots, 97.5)), 4))
        # permutation test on case-level means
        pooled = np.concatenate([pre_v, post_v])
        n_pre = len(pre_v)
        obs = abs(delta)
        cnt = 0
        NP = 10000
        for _ in range(NP):
            rng.shuffle(pooled)
            d = abs(pooled[n_pre:].mean() - pooled[:n_pre].mean())
            if d >= obs:
                cnt += 1
        perm_p = (cnt + 1) / (NP + 1)
        return {
            'pre_n_cases': int(len(pre_v)), 'post_n_cases': int(len(post_v)),
            'pre_macro_R@1': round(float(pre_v.mean()), 4),
            'post_macro_R@1': round(float(post_v.mean()), 4),
            'delta_pp': round(float(delta) * 100, 1),
            'delta_95CI_pp': [round(ci[0] * 100, 1), round(ci[1] * 100, 1)],
            'cluster_bootstrap_n': 10000,
            'permutation_p': round(perm_p, 4), 'permutation_n': NP,
        }

    macro_clean = case_macro(clean_ids['pre_cutoff'], clean_ids['post_cutoff'])

    # -------- 5. difficulty-matched sensitivity (case-level match) -----------
    feat_pre = holdout_features(DATASET['pre_cutoff'], prev)
    feat_post = holdout_features(DATASET['post_cutoff'], prev)
    # restrict to CLEAN cases first
    fp = {c: d for c, d in feat_pre.items() if c in clean_ids['pre_cutoff']}
    fq = {c: d for c, d in feat_post.items() if c in clean_ids['post_cutoff']}

    def balance(feats, key):
        return dict(Counter(feats[c][key] for c in feats))
    bal_before = {
        'pheno_bucket': {'pre': balance(fp, 'pheno_bkt'), 'post': balance(fq, 'pheno_bkt')},
        'prev_tier': {'pre': balance(fp, 'prev_tier'), 'post': balance(fq, 'prev_tier')},
    }
    unknown_prev = {
        'pre': round(sum(1 for c in fp if fp[c]['prev_tier'] in ('unknown', 'Unknown')) / len(fp), 3) if fp else None,
        'post': round(sum(1 for c in fq if fq[c]['prev_tier'] in ('unknown', 'Unknown')) / len(fq), 3) if fq else None,
    }
    # match on (pheno_bkt x prev_tier); keep min-count per stratum on both sides
    def strata(feats):
        s = defaultdict(list)
        for c, d in feats.items():
            s[(d['pheno_bkt'], d['prev_tier'])].append(c)
        return s
    sp, sq = strata(fp), strata(fq)
    matched_pre, matched_post = set(), set()
    for k in set(sp) & set(sq):
        m = min(len(sp[k]), len(sq[k]))
        matched_pre.update(sorted(sp[k])[:m])
        matched_post.update(sorted(sq[k])[:m])
    bal_after = {
        'pheno_bucket': {'pre': balance({c: fp[c] for c in matched_pre}, 'pheno_bkt'),
                         'post': balance({c: fq[c] for c in matched_post}, 'pheno_bkt')},
        'prev_tier': {'pre': balance({c: fp[c] for c in matched_pre}, 'prev_tier'),
                      'post': balance({c: fq[c] for c in matched_post}, 'prev_tier')},
    }
    # per-system on matched set
    matched_system_rows = []
    for sysname in SHARED_SYS:
        matched_system_rows.append(system_stat(sysname, matched_pre, matched_post))
    macro_matched = case_macro(matched_pre, matched_post)

    dm_fields = ['analysis', 'system', 'backbone', 'n_pre_attempted', 'n_post_attempted',
                 'pre_R@1_variant', 'post_R@1_variant', 'delta_R@1_pp', 'two_prop_z', 'p_raw']
    with open(OUT / 'temporal_holdout_difficulty_matched.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=dm_fields)
        w.writeheader()
        for r in matched_system_rows:
            w.writerow({'analysis': 'difficulty_matched', **{k: r.get(k) for k in dm_fields[1:]}})
        w.writerow({'analysis': 'difficulty_matched_MACRO', 'system': 'ALL_4_case_level',
                    'backbone': BB, 'n_pre_attempted': macro_matched['pre_n_cases'],
                    'n_post_attempted': macro_matched['post_n_cases'],
                    'pre_R@1_variant': macro_matched['pre_macro_R@1'],
                    'post_R@1_variant': macro_matched['post_macro_R@1'],
                    'delta_R@1_pp': macro_matched['delta_pp'],
                    'two_prop_z': '', 'p_raw': macro_matched['permutation_p']})

    # -------- 6. summary json + snapshot update ------------------------------
    direction_positive = all((r['delta_R@1_pp'] or 0) >= 0 for r in per_system_rows)
    summary = {
        'generated_at_utc': GEN_TIME,
        'commit': FROZEN_COMMIT,
        'data_version': DATA_VERSION,
        'generator': 'audit_frozen/temporal_v2/build_temporal_v2.py',
        'backbone': BB,
        'shared_systems': list(SHARED_SYS),
        'identity_model': {
            'keys_used': ['PMCID', 'PMID', 'source_case_id'],
            'keys_unavailable_in_frozen_data': ['DOI', 'normalized_title'],
            'note': 'DOI/title absent from every frozen artifact; exact-ID '
                    'intersection rests on PMCID (RareArena) + PMID (Phenopacket).',
        },
        'development_layers_intersected': {
            'rarearena_rds': 'PMCID (exact)',
            'phenopacket_store': 'PMID (exact)',
            'rarebench': 'NO publication id in shipped data -> NOT intersectable; '
                         'coverage gap, not asserted disjoint',
            'other_pmc_dev_cases': 'none present as case-report corpora in this checkout',
        },
        'overlap': overlap_meta,
        'clean_N': {s: overlap_meta[s]['n_clean'] for s in overlap_meta},
        'per_system_results': per_system_rows,
        'holm_correction': {'family_size': len(per_system_rows),
                            'systems': [r['system'] for r in per_system_rows],
                            'p_holm': {r['system']: r['p_holm'] for r in per_system_rows}},
        'case_level_macro_clean': macro_clean,
        'difficulty_matched': {
            'balance_before': bal_before, 'balance_after': bal_after,
            'unknown_prevalence_fraction': unknown_prev,
            'retained_cases': {'pre': len(matched_pre), 'post': len(matched_post)},
            'per_system': matched_system_rows,
            'case_level_macro': macro_matched,
            'role': 'sensitivity analysis; does NOT replace the full clean set',
        },
        'direction_all_systems_nonnegative': direction_positive,
        'allowed_conclusion': (
            'After removing cases overlapping with development data, none of the '
            'four evaluated systems showed detectable post-cutoff degradation.'),
        'forbidden_claims': [
            'the holdout is contamination-free',
            'memorization is not the driver',
            'post-cutoff performance is significantly better (unless case-clustered analysis supports it)',
            'after every model training cutoff (no official cutoff evidence)',
        ],
        'cutoff_language': 'published after the prespecified cutoff (NOT "guaranteed unseen by the models")',
    }
    (OUT / 'temporal_holdout_summary_v2.json').write_text(json.dumps(summary, indent=2, default=str))

    # patch results_snapshot.json (remove old contaminated pooled headline)
    snap_path = REPO / 'audit_frozen' / 'results_snapshot.json'
    snap = json.loads(snap_path.read_text())
    snap.pop('temporal_holdout', None)          # old status/values if present
    snap.pop('temporal_holdout_pooled', None)
    snap['temporal_holdout_v2'] = {
        'note': 'v1 pooled z-test treated each case x system as independent '
                '(pseudo-replication) and did NOT remove development overlaps; '
                'superseded by this clean, case-clustered analysis.',
        'clean_N': summary['clean_N'],
        'overlap_removed_union': {s: overlap_meta[s]['n_overlap_union'] for s in overlap_meta},
        'per_system': {r['system']: {
            'pre_R@1': r['pre_R@1_variant'], 'post_R@1': r['post_R@1_variant'],
            'delta_pp': r['delta_R@1_pp'], 'p_raw': r['p_raw'], 'p_holm': r['p_holm'],
            'n_pre': r['n_pre_attempted'], 'n_post': r['n_post_attempted']} for r in per_system_rows},
        'case_level_macro': macro_clean,
        'development_overlaps_found_and_removed': True,
        'allowed_conclusion': summary['allowed_conclusion'],
        'source_files': ['audit_frozen/temporal_v2/'],
    }
    snap_path.write_text(json.dumps(snap, indent=2, default=str))

    # console
    print('=== overlap ===')
    for s in overlap_meta:
        print(f"  {s}: total={overlap_meta[s]['n_total']} "
              f"by_source={overlap_meta[s]['overlap_by_source']} "
              f"union={overlap_meta[s]['n_overlap_union']} clean={overlap_meta[s]['n_clean']}")
    print('=== per-system (clean) ===')
    for r in per_system_rows:
        print(f"  {r['system']:11s} pre={r['pre_R@1_variant']}(n={r['n_pre_attempted']}) "
              f"post={r['post_R@1_variant']}(n={r['n_post_attempted']}) Δ={r['delta_R@1_pp']}pp "
              f"p_raw={r['p_raw']:.4f} p_holm={r['p_holm']:.4f}")
    print('=== case-level macro (clean) ===')
    print('  ', macro_clean)
    print('=== difficulty-matched macro ===')
    print('  ', macro_matched)
    print('  retained matched:', len(matched_pre), '/', len(matched_post))
    return summary


if __name__ == '__main__':
    main()

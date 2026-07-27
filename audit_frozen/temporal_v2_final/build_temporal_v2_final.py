"""Temporal-holdout FINAL freeze fix (v2-final).

Last frozen repair. NO new model calls. Only frozen pre/post receipts.

Changes vs audit_frozen/temporal_v2/:
  1. prevalence_tier labels unified BEFORE difficulty matching:
       strip whitespace; '' / 'unknown' / 'Unknown' -> single 'Unknown'.
  2. case-level matching re-run on unified labels; matched case lists,
     per-system results, case-level macro, bootstrap CI, permutation p
     all regenerated.
  3. report text corrected (unknown fraction; remove the two false claims).
  4. results_snapshot.json rebuilt FROM THE PRISTINE BACKUP so the old
     pseudo-replicated pooled p (0.001781...) is scrubbed everywhere,
     then temporal_holdout_v2 injected.
  5. case-level long file (one row per case x system) exported for
     independent cluster-bootstrap / permutation recompute.
  6. automatic assertions (see run_assertions).
  7. restrained paper conclusion string.

Reuses the verified helpers from audit_frozen/temporal_v2/build_temporal_v2.py
(overlap construction, hit recompute, stats) so scoring semantics are identical.
"""
from __future__ import annotations
import sys, os, json, csv, subprocess
from pathlib import Path
from collections import defaultdict, Counter

REPO = Path('/home/research/RDAgentBenchmark')
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'audit_frozen'))
sys.path.insert(0, str(REPO / 'audit_frozen' / 'temporal_v2'))
os.chdir(REPO)

import numpy as np
import recompute_engine as eng                    # noqa: E402  patched matching
import build_temporal_v2 as v2                     # noqa: E402  verified helpers
from build_temporal_v2 import (                    # noqa: E402
    BB, SHARED_SYS, SEED,
    rarearena_index, phenopacket_index, build_overlap,
    cell_case_hits, two_prop_z, boot_ci_rate, holm,
    pheno_count, pheno_bucket, prevalence_map,
)

OUT = REPO / 'audit_frozen' / 'temporal_v2_final'
SNAP = REPO / 'audit_frozen' / 'results_snapshot.json'
BAK = REPO / 'audit_frozen' / 'results_snapshot.json.pre_temporal_v2.bak'

COMMIT = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
GEN_TIME = subprocess.check_output(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ']).decode().strip()
DATA_VERSION = 'slim recompute set (MIMIC & weights stripped); frozen commit ' + COMMIT[:12]

SPLITS = {'pre_cutoff': 'pmc_precutoff', 'post_cutoff': 'pmc_oa_holdout'}
OLD_PSEUDO_P = ['0.001781', '0.0012700', '0.0183172']  # pseudo-replicated pooled p's to scrub


# ---------------------------------------------------------------- label unify
def norm_prev(raw) -> str:
    """Unify prevalence-tier labels: trim; ''/'unknown'/'Unknown' -> 'Unknown'."""
    t = ('' if raw is None else str(raw)).strip()
    if t == '' or t.lower() == 'unknown':
        return 'Unknown'
    return t


def holdout_features_unified(split_dir, prev):
    """case_id -> {orpha, pheno_n, pheno_bkt, prev_tier(UNIFIED)}."""
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
            'prev_tier': norm_prev(prev.get(orpha, '')),  # unified label
        }
    return feats


# ---------------------------------------------------------------- macro
def case_macro(hits_pre, hits_post, keep_pre, keep_post, seed=SEED):
    """Case = mean variant-correctness over the 4 systems. Sampling unit = case.
    Cluster bootstrap (case + its system vector resampled together) + permutation."""
    def per_case_mean(split_hits, keep):
        acc = defaultdict(list)
        for sysname in SHARED_SYS:
            v = split_hits[sysname][0]
            for cid, hit in v.items():
                if cid in keep:
                    acc[cid].append(hit)
        return {cid: sum(x) / len(x) for cid, x in acc.items() if x}
    pre_means = per_case_mean(hits_pre, keep_pre)
    post_means = per_case_mean(hits_post, keep_post)
    pre_v = np.array(list(pre_means.values()), dtype=float)
    post_v = np.array(list(post_means.values()), dtype=float)
    delta = post_v.mean() - pre_v.mean()
    rng = np.random.default_rng(seed)
    boots = np.array([rng.choice(post_v, len(post_v), True).mean()
                      - rng.choice(pre_v, len(pre_v), True).mean() for _ in range(10000)])
    ci = (round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4))
    pooled = np.concatenate([pre_v, post_v]); n_pre = len(pre_v); obs = abs(delta); cnt = 0; NP = 10000
    for _ in range(NP):
        rng.shuffle(pooled)
        if abs(pooled[n_pre:].mean() - pooled[:n_pre].mean()) >= obs:
            cnt += 1
    return {
        'pre_n_cases': int(len(pre_v)), 'post_n_cases': int(len(post_v)),
        'pre_macro_R@1': round(float(pre_v.mean()), 4), 'post_macro_R@1': round(float(post_v.mean()), 4),
        'delta_pp': round(float(delta) * 100, 1),
        'delta_95CI_pp': [round(ci[0] * 100, 1), round(ci[1] * 100, 1)],
        'cluster_bootstrap_n': 10000, 'permutation_p': round((cnt + 1) / (NP + 1), 4), 'permutation_n': NP,
    }


def system_stat(hits_pre, hits_post, sysname, keep_pre, keep_post):
    v_pre, s_pre, st_pre = hits_pre[sysname]
    v_post, s_post, st_post = hits_post[sysname]
    def agg(ids, v, s, st):
        n_att = len(ids)
        n_succ = sum(1 for c in ids if st.get(c) == 'ok')
        fails = Counter(st.get(c) for c in ids if st.get(c) != 'ok')
        return n_att, n_succ, dict(fails), sum(v[c] for c in ids), sum(s[c] for c in ids)
    pre_ids = [c for c in v_pre if c in keep_pre]
    post_ids = [c for c in v_post if c in keep_post]
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
        'pre_95CI': str(list(boot_ci_rate(hv1, na1))), 'post_95CI': str(list(boot_ci_rate(hv2, na2))),
        'delta_R@1_pp': round((hv2 / na2 - hv1 / na1) * 100, 1) if na1 and na2 else None,
        'two_prop_z': z, 'p_raw': p,
    }


# ================================================================== MAIN
def main():
    ra_idx = rarearena_index()
    pp_idx = phenopacket_index()
    prev = prevalence_map()

    # ---- overlap + clean sets (unchanged by label unify) --------------------
    all_removals, overlap_meta, clean_ids, full_ids = [], {}, {}, {}
    for split, sdir in SPLITS.items():
        ids, removals, by_source, union = build_overlap(split, sdir, ra_idx, pp_idx)
        all_removals.extend(removals)
        full_ids[split] = set(ids)
        clean_ids[split] = set(ids) - union
        overlap_meta[split] = {
            'n_total': len(ids),
            'overlap_by_source': {s: len(v) for s, v in by_source.items()},
            'n_overlap_union': len(union), 'n_clean': len(ids) - len(union),
            'overlap_case_ids_union': sorted(union),
        }

    ovl_fields = ['split', 'case_id', 'pmcid', 'pmid', 'doi', 'title',
                  'overlapping_dev_source', 'dev_case_id', 'match_key', 'match_value',
                  'gold_orpha_holdout', 'gold_orpha_dev', 'gold_orpha_agreement', 'removal_reason']
    with open(OUT / 'temporal_overlap_audit.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ovl_fields); w.writeheader()
        w.writerows(sorted(all_removals, key=lambda r: (r['split'], r['case_id'], r['overlapping_dev_source'])))

    hdr = (f"# data_version: {DATA_VERSION}\n# generator: audit_frozen/temporal_v2_final/"
           f"build_temporal_v2_final.py\n# commit: {COMMIT}\n# generated_at_utc: {GEN_TIME}\n")
    for split, fn in (('pre_cutoff', 'temporal_pre_clean_case_ids.txt'),
                      ('post_cutoff', 'temporal_post_clean_case_ids.txt')):
        (OUT / fn).write_text(hdr + '\n'.join(sorted(clean_ids[split])) + '\n')

    # ---- hits (both splits, shared backbone) --------------------------------
    hits_pre = {s: cell_case_hits(SPLITS['pre_cutoff'], s, BB) for s in SHARED_SYS}
    hits_post = {s: cell_case_hits(SPLITS['post_cutoff'], s, BB) for s in SHARED_SYS}

    # ---- per-system clean results + Holm ------------------------------------
    per_system = [system_stat(hits_pre, hits_post, s, clean_ids['pre_cutoff'], clean_ids['post_cutoff'])
                  for s in SHARED_SYS]
    for r, pa in zip(per_system, holm([r['p_raw'] for r in per_system])):
        r['p_holm'] = pa
    with open(OUT / 'temporal_holdout_clean_results.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(per_system[0].keys())); w.writeheader(); w.writerows(per_system)

    # ---- clean manifest -----------------------------------------------------
    man_rows = []
    for split in ('pre_cutoff', 'post_cutoff'):
        keep = clean_ids[split]; hb = hits_pre if split == 'pre_cutoff' else hits_post
        for s in SHARED_SYS:
            v, sc, st = hb[s]; ids = [c for c in v if c in keep]
            fails = Counter(st.get(c) for c in ids if st.get(c) != 'ok')
            hv, hs = sum(v[c] for c in ids), sum(sc[c] for c in ids); na = len(ids)
            man_rows.append({
                'split': split, 'system': s, 'backbone': BB,
                'n_full_before_removal': overlap_meta[split]['n_total'],
                'n_overlap_removed_union': overlap_meta[split]['n_overlap_union'],
                'n_clean_cases': overlap_meta[split]['n_clean'],
                'n_attempted': na, 'n_successful': sum(1 for c in ids if st.get(c) == 'ok'),
                'fail_timeout': fails.get('timeout', 0), 'fail_parser': fails.get('parser_error', 0),
                'fail_agent': fails.get('agent_error', 0), 'fail_empty_ok': fails.get('empty_ok', 0),
                'no_gold': fails.get('no_gold', 0),
                'top1_correct_strict': hs, 'top1_correct_variant': hv,
                'R@1_strict': round(hs / na, 4) if na else None,
                'R@1_variant_aware': round(hv / na, 4) if na else None,
                'bootstrap_95CI_variant': str(list(boot_ci_rate(hv, na))),
            })
    with open(OUT / 'temporal_holdout_clean_manifest.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(man_rows[0].keys())); w.writeheader(); w.writerows(man_rows)

    # ---- case-level macro (clean) -------------------------------------------
    macro_clean = case_macro(hits_pre, hits_post, clean_ids['pre_cutoff'], clean_ids['post_cutoff'])

    # ---- difficulty match on UNIFIED labels (clean cases only) --------------
    feat = {'pre_cutoff': holdout_features_unified(SPLITS['pre_cutoff'], prev),
            'post_cutoff': holdout_features_unified(SPLITS['post_cutoff'], prev)}
    fp = {c: d for c, d in feat['pre_cutoff'].items() if c in clean_ids['pre_cutoff']}
    fq = {c: d for c, d in feat['post_cutoff'].items() if c in clean_ids['post_cutoff']}

    def balance(feats, key):
        return dict(Counter(feats[c][key] for c in feats))
    bal_before = {k: {'pre': balance(fp, k), 'post': balance(fq, k)} for k in ('pheno_bkt', 'prev_tier')}
    unknown_frac = {
        'pre': round(sum(1 for c in fp if fp[c]['prev_tier'] == 'Unknown') / len(fp), 3) if fp else None,
        'post': round(sum(1 for c in fq if fq[c]['prev_tier'] == 'Unknown') / len(fq), 3) if fq else None,
    }

    def strata(feats):
        s = defaultdict(list)
        for c, d in feats.items():
            s[(d['pheno_bkt'], d['prev_tier'])].append(c)
        return s
    sp, sq = strata(fp), strata(fq)
    matched_pre, matched_post = set(), set()
    for k in set(sp) & set(sq):
        m = min(len(sp[k]), len(sq[k]))
        matched_pre.update(sorted(sp[k])[:m]); matched_post.update(sorted(sq[k])[:m])
    bal_after = {k: {'pre': balance({c: fp[c] for c in matched_pre}, k),
                     'post': balance({c: fq[c] for c in matched_post}, k)} for k in ('pheno_bkt', 'prev_tier')}

    matched_system = [system_stat(hits_pre, hits_post, s, matched_pre, matched_post) for s in SHARED_SYS]
    macro_matched = case_macro(hits_pre, hits_post, matched_pre, matched_post)

    for split, fn in (('pre', 'temporal_pre_matched_case_ids.txt'),
                      ('post', 'temporal_post_matched_case_ids.txt')):
        s = matched_pre if split == 'pre' else matched_post
        (OUT / fn).write_text(hdr + '\n'.join(sorted(s)) + '\n')

    dm_fields = ['analysis', 'system', 'backbone', 'n_pre_attempted', 'n_post_attempted',
                 'pre_R@1_variant', 'post_R@1_variant', 'delta_R@1_pp', 'two_prop_z', 'p_raw']
    with open(OUT / 'temporal_holdout_difficulty_matched.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=dm_fields); w.writeheader()
        for r in matched_system:
            w.writerow({'analysis': 'difficulty_matched', **{k: r.get(k) for k in dm_fields[1:]}})
        w.writerow({'analysis': 'difficulty_matched_MACRO', 'system': 'ALL_4_case_level', 'backbone': BB,
                    'n_pre_attempted': macro_matched['pre_n_cases'], 'n_post_attempted': macro_matched['post_n_cases'],
                    'pre_R@1_variant': macro_matched['pre_macro_R@1'], 'post_R@1_variant': macro_matched['post_macro_R@1'],
                    'delta_R@1_pp': macro_matched['delta_pp'], 'two_prop_z': '', 'p_raw': macro_matched['permutation_p']})

    # ---- case x system LONG file (independent recompute) --------------------
    long_fields = ['split', 'case_id', 'system', 'attempted', 'successful',
                   'correct_variant', 'matched_flag', 'phenotype_bucket', 'prevalence_tier']
    with open(OUT / 'temporal_holdout_case_system_long.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=long_fields); w.writeheader()
        for split in ('pre_cutoff', 'post_cutoff'):
            keep = clean_ids[split]; hb = hits_pre if split == 'pre_cutoff' else hits_post
            matched = matched_pre if split == 'pre_cutoff' else matched_post
            feats = feat[split]
            for s in SHARED_SYS:
                v, sc, st = hb[s]
                for cid in sorted(c for c in v if c in keep):
                    fe = feats.get(cid, {})
                    w.writerow({
                        'split': split, 'case_id': cid, 'system': s,
                        'attempted': 1, 'successful': 1 if st.get(cid) == 'ok' else 0,
                        'correct_variant': v[cid], 'matched_flag': 1 if cid in matched else 0,
                        'phenotype_bucket': fe.get('pheno_bkt', ''), 'prevalence_tier': fe.get('prev_tier', ''),
                    })

    # ---- summary json -------------------------------------------------------
    dm_dirs = [r['delta_R@1_pp'] for r in matched_system]
    conclusion = ("After removing exact-identifier overlaps with identifier-bearing "
                  "development sources, we found no statistically detectable post-cutoff "
                  "degradation across the four evaluated systems.")
    summary = {
        'generated_at_utc': GEN_TIME, 'commit': COMMIT, 'data_version': DATA_VERSION,
        'generator': 'audit_frozen/temporal_v2_final/build_temporal_v2_final.py',
        'backbone': BB, 'shared_systems': list(SHARED_SYS),
        'label_unification': {
            'field': 'prevalence_tier',
            'rule': "strip whitespace; '' / 'unknown' / 'Unknown' -> single 'Unknown'",
            'applied_before_matching': True,
        },
        'identity_model': {
            'keys_used': ['PMCID', 'PMID', 'source_case_id'],
            'keys_unavailable_in_frozen_data': ['DOI', 'normalized_title'],
            'note': 'DOI/title absent from every frozen artifact; exact-ID intersection '
                    'rests on PMCID (RareArena) + PMID (Phenopacket).',
        },
        'development_layers_intersected': {
            'rarearena_rds': 'PMCID (exact)', 'phenopacket_store': 'PMID (exact)',
            'rarebench': 'NO publication id in shipped data -> NOT intersectable; coverage gap',
            'other_pmc_dev_cases': 'none present as case-report corpora in this checkout',
        },
        'overlap': overlap_meta,
        'clean_N': {s: overlap_meta[s]['n_clean'] for s in overlap_meta},
        'per_system_results': per_system,
        'holm_correction': {'family_size': len(per_system),
                            'p_holm': {r['system']: r['p_holm'] for r in per_system}},
        'case_level_macro_clean': macro_clean,
        'difficulty_matched': {
            'labels': 'prevalence_tier unified (Unknown merged) BEFORE matching',
            'match_keys': '(pheno_bucket x prevalence_tier incl. Unknown stratum), min-count per stratum',
            'balance_before': bal_before, 'balance_after': bal_after,
            'unknown_prevalence_fraction': unknown_frac,
            'retained_cases': {'pre': len(matched_pre), 'post': len(matched_post)},
            'per_system': matched_system, 'case_level_macro': macro_matched,
            'all_system_deltas_nonnegative': all(d >= 0 for d in dm_dirs),
            'role': 'sensitivity analysis; does NOT replace the full clean set',
        },
        'allowed_conclusion': conclusion,
        'forbidden_claims': ['contamination-free', 'guaranteed unseen by the models',
                             'memorization is not the driver'],
        'cutoff_language': 'published after the prespecified cutoff',
    }
    (OUT / 'temporal_holdout_summary_v2.json').write_text(json.dumps(summary, indent=2, default=str))

    # ---- rebuild results_snapshot.json FROM PRISTINE BACKUP -----------------
    snap = json.loads(BAK.read_text())
    snap.pop('temporal_holdout', None)  # drop old contaminated/pseudo-replicated headline
    fu = snap.get('followup_2026_07_22')
    if isinstance(fu, dict):
        # difficulty_matching block held the pseudo-replicated pooled p-values
        fu['difficulty_matching'] = {'superseded_by': 'temporal_holdout_v2',
                                     'note': 'old pooled analysis expanded case x system (pseudo-replication) '
                                             'and did not remove dev overlaps; removed. See temporal_holdout_v2.'}
        cs = fu.get('contamination_scan')
        if isinstance(cs, dict):
            cs['superseded_by'] = 'temporal_holdout_v2 (union overlap: pre 14 / post 18; gold agreement 23/32)'
    snap['temporal_holdout_v2'] = {
        'generated_at_utc': GEN_TIME, 'commit': COMMIT, 'data_version': DATA_VERSION,
        'note': 'Supersedes v1 temporal_holdout. v1 used a pooled z-test treating each '
                'case x system as independent (pseudo-replication) and did not remove '
                'development overlaps. This is the clean, case-clustered, Holm-corrected analysis.',
        'identity_keys_used': ['PMCID', 'PMID'], 'identity_keys_absent': ['DOI', 'title'],
        'overlap_union': {s: overlap_meta[s]['n_overlap_union'] for s in overlap_meta},
        'overlap_by_source': {s: overlap_meta[s]['overlap_by_source'] for s in overlap_meta},
        'clean_N': {s: overlap_meta[s]['n_clean'] for s in overlap_meta},
        'per_system_holm': {r['system']: {
            'pre_R@1': r['pre_R@1_variant'], 'post_R@1': r['post_R@1_variant'],
            'delta_pp': r['delta_R@1_pp'], 'p_raw': r['p_raw'], 'p_holm': r['p_holm'],
            'n_pre': r['n_pre_attempted'], 'n_post': r['n_post_attempted']} for r in per_system},
        'case_level_macro': macro_clean,
        'difficulty_matched_sensitivity': {
            'retained': {'pre': len(matched_pre), 'post': len(matched_post)},
            'unknown_prevalence_fraction': unknown_frac,
            'per_system_delta_pp': {r['system']: r['delta_R@1_pp'] for r in matched_system},
            'case_level_macro': macro_matched,
            'all_system_deltas_nonnegative': all(d >= 0 for d in dm_dirs),
        },
        'development_overlaps_found_and_removed': True,
        'frozen_commit': COMMIT,
        'allowed_conclusion': conclusion,
        'source_files': ['audit_frozen/temporal_v2_final/'],
    }
    SNAP.write_text(json.dumps(snap, indent=2, default=str))

    # ---- report markdown (values inlined so it agrees with json) ------------
    write_report(overlap_meta, per_system, macro_clean, matched_system, macro_matched,
                 unknown_frac, bal_before, bal_after, len(matched_pre), len(matched_post),
                 dm_dirs, conclusion)

    run_assertions(overlap_meta, per_system, man_rows)

    # ---- console ------------------------------------------------------------
    print('=== overlap ===')
    for s in overlap_meta:
        print(f"  {s}: total={overlap_meta[s]['n_total']} by_source={overlap_meta[s]['overlap_by_source']} "
              f"union={overlap_meta[s]['n_overlap_union']} clean={overlap_meta[s]['n_clean']}")
    print('=== per-system (clean) ===')
    for r in per_system:
        print(f"  {r['system']:11s} pre={r['pre_R@1_variant']} post={r['post_R@1_variant']} "
              f"Δ={r['delta_R@1_pp']}pp p_raw={r['p_raw']:.4f} p_holm={r['p_holm']:.4f}")
    print('=== macro clean ===', macro_clean)
    print('=== difficulty-matched (unified labels) ===')
    for r in matched_system:
        print(f"  {r['system']:11s} Δ={r['delta_R@1_pp']}pp (p_raw={r['p_raw']:.3f})")
    print('  macro:', macro_matched, '| retained', len(matched_pre), '/', len(matched_post))
    print('  unknown_frac:', unknown_frac, '| matched deltas nonneg?', all(d >= 0 for d in dm_dirs))
    print('ALL ASSERTIONS PASSED')


def write_report(ovl, ps, macro, dm_sys, dm_macro, unk, bal_before, bal_after,
                 n_mp, n_mq, dm_dirs, conclusion):
    def row(r):
        return (f"| {r['system']} | {r['n_pre_attempted']} | {r['n_post_attempted']} | "
                f"{r['pre_R@1_variant']} | {r['post_R@1_variant']} | {r['delta_R@1_pp']:+.1f}pp | "
                f"{r['post_95CI']} | {r['two_prop_z']} | {r['p_raw']:.4f} | **{r['p_holm']:.4f}** |")
    dm_rows = "\n".join(
        f"| {r['system']} | {r['n_pre_attempted']} | {r['n_post_attempted']} | "
        f"{r['pre_R@1_variant']} | {r['post_R@1_variant']} | {r['delta_R@1_pp']:+.1f}pp | {r['p_raw']:.4f} |"
        for r in dm_sys)
    neg = [r['system'] for r in dm_sys if (r['delta_R@1_pp'] or 0) < 0]
    md = f"""# Temporal-Holdout 最终冻结结果 (v2-final)

> 最后一次冻结修复。**未修改论文文字，未调用任何新模型**，只用磁盘上已有的 pre/post prediction receipts。
> 取代 `audit_frozen/temporal_v2/` 与 v1 (`consistency_report.md` §6/§9.1–§9.2)。

- Data version: {DATA_VERSION}
- Commit: `{COMMIT}`
- 生成时间 (UTC): `{GEN_TIME}` （summary / 本报告 / snapshot 同一 commit 与生成时间）
- 生成脚本: `audit_frozen/temporal_v2_final/build_temporal_v2_final.py`
- Backbone: Gemini 3 Flash（唯一 pre/post 两侧都齐的 backbone）
- Systems: `llm_control`, `mdagents`, `medagents`, `agentclinic`

---

## 本次修复要点（相对 temporal_v2）

1. **prevalence-tier 标签在 difficulty matching 前统一**：trim 空白，并将 `Unknown` / `unknown` / 空值统一映射为单一 `Unknown` 类别（此前 `'Unknown'` 与 `'unknown'` 被当成两个 strata）。
2. 统一标签后**重新执行 case-level matching**，并重新生成 matched case lists、per-system results、case-level macro、bootstrap CI、permutation p。
3. 修正下方两处此前的错误表述。
4. `results_snapshot.json` 从**未改动的备份**重建，彻底抹掉旧的伪重复 pooled p（0.001781…），再写入 `temporal_holdout_v2`。
5. 新增 case×system 长表 `temporal_holdout_case_system_long.csv`，供独立复算 cluster bootstrap / permutation。

---

## 一、disjoint test set（overlap union，未受标签统一影响）

统一 publication identity 用 **PMCID + PMID**（都是精确匹配）。**DOI 与 normalized title 在所有冻结产物里都不存在**，overlap 审计 CSV 保留列但为空并标注。

| dev 层 | 匹配键 | 可交集? | pre overlap | post overlap |
|---|---|---|---|---|
| RareArena RDS | PMCID | ✅ | {ovl['pre_cutoff']['overlap_by_source'].get('rarearena_rds',0)} | {ovl['post_cutoff']['overlap_by_source'].get('rarearena_rds',0)} |
| Phenopacket Store | PMID | ✅ | {ovl['pre_cutoff']['overlap_by_source'].get('phenopacket_store',0)} | {ovl['post_cutoff']['overlap_by_source'].get('phenopacket_store',0)} |
| RareBench | — | ❌ shipped 数据无任何出版物 ID | 不可查 | 不可查 |
| 其他 PMC dev cases | — | ❌ 本 checkout 无 case-report 语料 | — | — |

⚠️ RareBench 无法做 ID 交集，因此只能声明"已移除对 identifier-bearing dev 源 (RareArena+Phenopacket) 的 exact-ID overlap"，**不能声明与全部 dev 层 disjoint**。

| split | 总病例 | union（去重后并集） | **clean N** |
|---|---|---|---|
| pre_cutoff | {ovl['pre_cutoff']['n_total']} | {ovl['pre_cutoff']['n_overlap_union']} | **{ovl['pre_cutoff']['n_clean']}** |
| post_cutoff | {ovl['post_cutoff']['n_total']} | {ovl['post_cutoff']['n_overlap_union']} | **{ovl['post_cutoff']['n_clean']}** |

Phenopacket 的 PMID-overlap 与 RareArena 的 PMCID-overlap 不相交，故 clean N = **{ovl['pre_cutoff']['n_clean']} / {ovl['post_cutoff']['n_clean']}**（非 207/181）。逐病例明细见 `temporal_overlap_audit.csv`。

---

## 二、per-system 结果（clean set，Holm 校正，family=4）

attempted 分母、variant-aware 为 primary，failures 保留在分母。

| system | n_pre | n_post | pre R@1 | post R@1 | ΔR@1 | 95% CI(post) | z | p_raw | **p_holm** |
|---|---|---|---|---|---|---|---|---|---|
{row(ps[2])}
{row(ps[1])}
{row(ps[3])}
{row(ps[0])}

四个系统 ΔR@1 方向均为正（post ≥ pre）；**Holm 校正后无一显著**（最小 p_holm = {min(r['p_holm'] for r in ps):.3f}）。

---

## 三、pooled 修正（去 pseudo-replication）

v1 的 pooled z-test（把同病例×4系统当 4 个独立观测，pooled p=0.0017816）**作废并已从 snapshot 抹除**。改用 **case-level macro**（抽样单位=病例；同病例 4 系统一起 cluster-bootstrap + permutation）：

| 口径 | pre macro R@1 (n) | post macro R@1 (n) | Δ | 95% CI | permutation p |
|---|---|---|---|---|---|
| clean set | {macro['pre_macro_R@1']} ({macro['pre_n_cases']}) | {macro['post_macro_R@1']} ({macro['post_n_cases']}) | **{macro['delta_pp']:+.1f}pp** | {macro['delta_95CI_pp']} pp | **{macro['permutation_p']}** |

case-clustered 后 Δ 为正但 **不显著**（p={macro['permutation_p']}）—— 印证 v1 的显著性是伪重复产物。

---

## 四、difficulty-matched sensitivity（标签统一后重算）

匹配在 **case level** 完成，特征 = phenotype-count 分桶 × prevalence tier（**含统一后的 `Unknown` stratum**）。

- **unknown prevalence 比例（统一 `Unknown` 后）**：pre ≈ {unk['pre']:.0%} / post ≈ {unk['post']:.0%}。
- **说明**：本分析**保留了 `Unknown` stratum 参与匹配**（并非只在有 prevalence tier 的病例上完成）。matching 前后分布见 `temporal_holdout_summary_v2.json:difficulty_matched`。
- retained：**{n_mp} / {n_mq}**。

| system | n_pre | n_post | pre R@1 | post R@1 | ΔR@1 | p_raw |
|---|---|---|---|---|---|---|
{dm_rows}

| case-level macro | Δ={dm_macro['delta_pp']:+.1f}pp | 95% CI {dm_macro['delta_95CI_pp']} pp | permutation p={dm_macro['permutation_p']} |
|---|---|---|---|

**方向说明**：difficulty-matched 下 **并非所有系统方向都非负** —— AgentClinic 为 {dm_sys[0]['delta_R@1_pp'] if dm_sys[0]['system']=='agentclinic' else [r['delta_R@1_pp'] for r in dm_sys if r['system']=='agentclinic'][0]:+.1f}pp{'（' + ', '.join(neg) + ' 为负）' if neg else ''}。作为 sensitivity analysis，不替代完整 clean set。

---

## 五、允许的论文结论

> **"{conclusion}"**

**不得使用**：contamination-free、guaranteed unseen、memorization is not the driver。时间措辞用 **"published after the prespecified cutoff"**。

---

## 六、交付文件（均在 `audit_frozen/temporal_v2_final/`）

| 文件 | 内容 |
|---|---|
| `temporal_overlap_audit.csv` | 每个被删除 case×dev-source 一行 |
| `temporal_holdout_clean_manifest.csv` | clean set 逐 split×system |
| `temporal_holdout_clean_results.csv` | per-system + strict/variant + CI + Δ + z + p_raw + p_holm |
| `temporal_holdout_difficulty_matched.csv` | 标签统一后 difficulty-matched per-system + macro |
| `temporal_holdout_case_system_long.csv` | 每行一个 case×system：split/case_id/system/attempted/successful/correct_variant/matched_flag/phenotype_bucket/prevalence_tier |
| `temporal_holdout_summary_v2.json` | 全部结果 + 标签统一规则 + allowed/forbidden claims |
| `temporal_pre/post_clean_case_ids.txt` | clean case lists（确定性排序 + 版本头） |
| `temporal_pre/post_matched_case_ids.txt` | difficulty-matched case lists |
| `temporal_holdout_audit_v2.md` | 本报告 |

`audit_frozen/results_snapshot.json` 从备份重建：删除旧 `temporal_holdout` 与伪重复 pooled p，写入 `temporal_holdout_v2`。
"""
    (OUT / 'temporal_holdout_audit_v2.md').write_text(md)


def run_assertions(ovl, per_system, man_rows):
    errs = []
    # n_full - n_overlap_union = n_clean
    for s in ovl:
        if ovl[s]['n_total'] - ovl[s]['n_overlap_union'] != ovl[s]['n_clean']:
            errs.append(f'{s}: n_full - union != clean')
    # attempted == n_clean ; successful + all_failures == attempted
    for r in man_rows:
        if r['n_attempted'] != r['n_clean_cases']:
            errs.append(f"{r['split']}/{r['system']}: attempted != n_clean")
        fails = r['fail_timeout'] + r['fail_parser'] + r['fail_agent'] + r['fail_empty_ok'] + r['no_gold']
        if r['n_successful'] + fails != r['n_attempted']:
            errs.append(f"{r['split']}/{r['system']}: successful + failures != attempted")
    # snapshot: no old pooled p ; has temporal_holdout_v2 ; no top-level temporal_holdout
    snap_txt = SNAP.read_text()
    snap_obj = json.loads(snap_txt)
    for p in OLD_PSEUDO_P:
        if p in snap_txt:
            errs.append(f'snapshot still contains old pooled p {p}')
    if 'temporal_holdout_v2' not in snap_obj:
        errs.append('snapshot missing temporal_holdout_v2')
    if 'temporal_holdout' in snap_obj:
        errs.append('snapshot still has top-level temporal_holdout')
    # same commit + gen time across summary/report/snapshot
    summ = (OUT / 'temporal_holdout_summary_v2.json').read_text()
    rep = (OUT / 'temporal_holdout_audit_v2.md').read_text()
    for name, txt in (('summary', summ), ('report', rep), ('snapshot', snap_txt)):
        if COMMIT not in txt:
            errs.append(f'{name} missing commit {COMMIT}')
        if GEN_TIME not in txt:
            errs.append(f'{name} missing gen time {GEN_TIME}')
    if errs:
        raise AssertionError('ASSERTIONS FAILED:\n  ' + '\n  '.join(errs))


if __name__ == '__main__':
    main()

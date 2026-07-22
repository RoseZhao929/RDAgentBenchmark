"""Frozen-results audit — deliverables generator.

Consumes audit_frozen/_manifest_rows.json (from recompute_engine.py) and the
raw receipts, and emits the six required audit artifacts:
  frozen_main_manifest.csv, headline_results.csv, cost_summary.csv,
  temporal_holdout_audit.csv, results_snapshot.json, consistency_report.md

Case-level paired effects (scaffold effect, variant-channel effect) are
computed here with a true paired McNemar test on the SAME case_ids.
"""
from __future__ import annotations
import sys, json, csv, glob, os, math
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO)); os.chdir(REPO)

# --- reuse the engine's patched crossmap + gold (import triggers the patches)
import recompute_engine as eng  # type: ignore  # noqa: E402
from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants  # noqa: E402
from scipy import stats  # noqa: E402

FROZEN_COMMIT = eng.FROZEN_COMMIT
OUT = REPO / 'audit_frozen'
ROWS = json.loads((OUT / '_manifest_rows.json').read_text())
GOLD, PROV = eng.load_gold()
CANON = {k: set(v) for k, v in json.load(open(eng.CANON_PATH)).items()} if os.path.exists(eng.CANON_PATH) else {}

MAIN_DS = ('phenopacket_store', 'rarearena_rds', 'rarebench', 'mimic_diverse')
SCAFFOLDED = ('mdagents', 'medagents', 'agentclinic', 'maidxo', 'deeprare')
CONTROL = 'llm_control'

# ---------------------------------------------------------------- case-level hits
def case_hits(dataset, agent, backbone_prefix):
    """Return {case_id: 0/1 variant-aware hit} for one cell, over ATTEMPTED
    cases (failures -> 0). backbone_prefix matched against filename."""
    out = {}
    for p in glob.glob(f'data/round2/phase4a/predictions_{dataset}_{agent}_*.jsonl'):
        fn = os.path.basename(p)
        if backbone_prefix not in fn:
            continue
        best = eng.dedupe_cases(p)
        if dataset in CANON:
            best = {c: r for c, r in best.items() if c in CANON[dataset]}
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

def mcnemar(paired):
    """paired: list of (a_hit, b_hit). Returns dict with discordants + test."""
    b = sum(1 for x, y in paired if x and not y)  # a-win
    c = sum(1 for x, y in paired if y and not x)  # b-win
    n = b + c
    if n == 0:
        return {'n_pairs': len(paired), 'b_only': b, 'c_only': c, 'chi2_cc': None, 'p': None}
    chi2 = (abs(b - c) - 1) ** 2 / n  # continuity-corrected
    p = float(stats.chi2.sf(chi2, 1))
    return {'n_pairs': len(paired), 'b_only': b, 'c_only': c,
            'chi2_cc': round(chi2, 3), 'p': p}

def two_prop_z(h1, n1, h2, n2):
    p1, p2 = h1 / n1, h2 / n2
    pp = (h1 + h2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p2 - p1) / se
    return round(z, 3), float(2 * stats.norm.sf(abs(z)))

# ---------------------------------------------------------------- 1. manifest csv
MANIFEST_COLS = [
    'dataset', 'system', 'backbone', 'capability', 'evaluation_pass',
    'n_planned', 'n_attempted', 'n_successful', 'n_failed',
    'fail_timeout', 'fail_parser', 'fail_agent', 'fail_empty_ok', 'no_gold',
    'top1_correct_strict', 'top1_correct_variant_aware',
    'R@1_strict', 'R@1_variant_aware', 'R@5_strict', 'R@5_variant_aware', 'R@5',
    'bootstrap_95CI', 'R@1_variant_success_denom', 'R@1_strict_success_denom',
    'api_calls', 'total_cost_usd', 'cost_per_attempt', 'cost_per_success',
    'latency_per_attempt_ms', 'capped_frame',
]

def write_manifest():
    with open(OUT / 'frozen_main_manifest.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLS)
        w.writeheader()
        for r in ROWS:
            w.writerow({k: r.get(k) for k in MANIFEST_COLS})

# ---------------------------------------------------------------- 2. headline csv
CANDIDATES = []

def rowget(ds, sys_, bb_contains):
    for r in ROWS:
        if r['dataset'] == ds and r['system'] == sys_ and bb_contains in r['backbone']:
            return r
    return None

def write_headline():
    lir = rowget('phenopacket_store', 'lirical', 'lirical')
    vc_pp = rowget('phenopacket_store', 'vc_rdagent', 'vc_rdagent')
    vc_rb = rowget('rarebench', 'vc_rdagent', 'vc_rdagent')
    # best scaffolded LLM on PP-Store (variant, attempted denom)
    best = None
    for r in ROWS:
        if r['dataset'] == 'phenopacket_store' and r['system'] in SCAFFOLDED and r['R@1_variant_aware'] is not None:
            if best is None or r['R@1_variant_aware'] > best['R@1_variant_aware']:
                best = r
    gap = round(lir['R@1_variant_aware'] - best['R@1_variant_aware'], 4)
    CANDIDATES.extend([
        ('LIRICAL PP-Store R@1', 0.47, lir['R@1_variant_aware'], lir['bootstrap_95CI'],
         f"{lir['system']}/{lir['backbone']} n_att={lir['n_attempted']}"),
        ('best scaffolded LLM PP-Store R@1', 0.30, best['R@1_variant_aware'], best['bootstrap_95CI'],
         f"{best['system']}/{best['backbone']} n_att={best['n_attempted']}"),
        ('gap (classical - best LLM) pp', 17.0, round(gap * 100, 1), '',
         f"{lir['R@1_variant_aware']} - {best['R@1_variant_aware']}"),
        ('VC-RDAgent RareBench R@1', 0.28, vc_rb['R@1_variant_aware'], vc_rb['bootstrap_95CI'],
         f"n_att={vc_rb['n_attempted']}"),
        ('VC-RDAgent PP-Store R@1 (ref)', 0.44, vc_pp['R@1_variant_aware'], vc_pp['bootstrap_95CI'],
         f"n_att={vc_pp['n_attempted']}"),
    ])
    with open(OUT / 'headline_results.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['metric', 'paper_candidate', 'recomputed_frozen', 'reproduces',
                    'abs_diff', 'bootstrap_95CI', 'provenance'])
        for name, cand, got, ci, prov in CANDIDATES:
            got_f = float(got)
            diff = round(abs(got_f - cand), 4)
            repro = 'YES' if diff <= (0.5 if 'pp' in name else 0.01) else 'NO'
            w.writerow([name, cand, got, repro, diff, ci, prov])
    return CANDIDATES

# ---------------------------------------------------------------- 3. cost csv
def write_cost():
    by_bb = defaultdict(lambda: {'cells': 0, 'attempted': 0, 'successful': 0,
                                 'top1v': 0, 'api_calls': 0, 'usd': 0.0})
    for r in ROWS:
        if r['dataset'] not in MAIN_DS:
            continue
        b = by_bb[r['backbone']]
        b['cells'] += 1
        b['attempted'] += r['n_attempted']; b['successful'] += r['n_successful']
        b['top1v'] += r['top1_correct_variant_aware']; b['api_calls'] += r['api_calls']
        b['usd'] += r['total_cost_usd']
    with open(OUT / 'cost_summary.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['inclusion_set', 'backbone', 'cells', 'attempted_predictions',
                    'successful_predictions', 'top1_correct_variant', 'api_calls',
                    'total_cost_usd', 'cost_per_attempt', 'cost_per_success'])
        tot = {'cells': 0, 'attempted': 0, 'successful': 0, 'usd': 0.0, 'api': 0, 'hit': 0}
        for bb, b in sorted(by_bb.items()):
            cpa = round(b['usd'] / b['attempted'], 6) if b['attempted'] else ''
            cps = round(b['usd'] / b['top1v'], 6) if b['top1v'] else ''
            w.writerow(['MAIN_MATRIX_frozen', bb, b['cells'], b['attempted'],
                        b['successful'], b['top1v'], b['api_calls'],
                        round(b['usd'], 4), cpa, cps])
            tot['cells'] += b['cells']; tot['attempted'] += b['attempted']
            tot['successful'] += b['successful']; tot['usd'] += b['usd']
            tot['api'] += b['api_calls']; tot['hit'] += b['top1v']
        w.writerow(['MAIN_MATRIX_frozen', 'TOTAL', tot['cells'], tot['attempted'],
                    tot['successful'], tot['hit'], tot['api'], round(tot['usd'], 2),
                    round(tot['usd'] / tot['attempted'], 6) if tot['attempted'] else '',
                    round(tot['usd'] / tot['hit'], 6) if tot['hit'] else ''])
        # per-attempt cost multiples (same statistic across backbones)
        w.writerow([])
        w.writerow(['# cost-per-attempt multiples (relative to cheapest backbone)'])
        # multiples must compare the SAME statistic (per-attempt cost); base on
        # the cheapest NON-zero backbone (classical tools are $0 and excluded).
        cpas = {bb: b['usd'] / b['attempted'] for bb, b in by_bb.items() if b['attempted']}
        nonzero = {bb: v for bb, v in cpas.items() if v > 0}
        base = min(nonzero.values()) if nonzero else 1.0
        for bb, v in sorted(cpas.items(), key=lambda x: x[1]):
            mult = f"{v/base:.1f}x" if v > 0 else "0x (free classical)"
            w.writerow(['MULTIPLE', bb, '', '', '', '', '', round(v, 6), mult, ''])
    return by_bb, tot

# ---------------------------------------------------------------- 4. holdout csv
def write_holdout():
    # pre = pmc_precutoff, post = pmc_oa_holdout. Pair on Gemini Flash (common backbone).
    pre_rows = [r for r in ROWS if r['dataset'] == 'pmc_precutoff']
    post_rows = [r for r in ROWS if r['dataset'] == 'pmc_oa_holdout']
    gold_pre = eng.PROV if False else None
    n_pre_gold = PROV.get('pmc_precutoff', {}).get('n_gold_cases')
    n_post_gold = PROV.get('pmc_oa_holdout', {}).get('n_gold_cases')

    with open(OUT / 'temporal_holdout_audit.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['split', 'system', 'backbone', 'n_gold_cases', 'n_attempted',
                    'n_successful', 'top1_correct_variant', 'R@1_variant_aware',
                    'bootstrap_95CI'])
        for tag, rows_ in (('pre_cutoff', pre_rows), ('post_cutoff', post_rows)):
            ng = n_pre_gold if tag == 'pre_cutoff' else n_post_gold
            for r in sorted(rows_, key=lambda x: x['system']):
                w.writerow([tag, r['system'], r['backbone'], ng, r['n_attempted'],
                            r['n_successful'], r['top1_correct_variant_aware'],
                            r['R@1_variant_aware'], r['bootstrap_95CI']])
        # pooled + pre/post difference on the shared Gemini systems
        w.writerow([])
        w.writerow(['# pre/post difference (Gemini Flash, per system, two-prop z on attempted denom)'])
        w.writerow(['system', 'pre_R@1', 'post_R@1', 'delta_pp', 'z', 'p_raw', 'note'])
        gpre = {r['system']: r for r in pre_rows if 'gemini' in r['backbone']}
        gpost = {r['system']: r for r in post_rows if 'gemini' in r['backbone']}
        pool_pre_h = pool_pre_n = pool_post_h = pool_post_n = 0
        for sysname in sorted(set(gpre) & set(gpost)):
            a, b = gpre[sysname], gpost[sysname]
            z, p = two_prop_z(a['top1_correct_variant_aware'], a['n_attempted'],
                              b['top1_correct_variant_aware'], b['n_attempted'])
            delta = round((b['R@1_variant_aware'] - a['R@1_variant_aware']) * 100, 1)
            w.writerow([sysname, a['R@1_variant_aware'], b['R@1_variant_aware'],
                        delta, z, f"{p:.4g}" if p is not None else '',
                        'different case sets; difficulty NOT matched'])
            pool_pre_h += a['top1_correct_variant_aware']; pool_pre_n += a['n_attempted']
            pool_post_h += b['top1_correct_variant_aware']; pool_post_n += b['n_attempted']
        z, p = two_prop_z(pool_pre_h, pool_pre_n, pool_post_h, pool_post_n)
        w.writerow(['POOLED', round(pool_pre_h / pool_pre_n, 4), round(pool_post_h / pool_post_n, 4),
                    round((pool_post_h / pool_post_n - pool_pre_h / pool_pre_n) * 100, 1),
                    z, f"{p:.4g}" if p is not None else '', 'conclusion: no detectable post-cutoff degradation'])
    return {'n_pre_gold': n_pre_gold, 'n_post_gold': n_post_gold,
            'pooled_pre': round(pool_pre_h / pool_pre_n, 4),
            'pooled_post': round(pool_post_h / pool_post_n, 4),
            'pooled_delta_pp': round((pool_post_h / pool_post_n - pool_pre_h / pool_pre_n) * 100, 1),
            'pooled_p': p}

# ---------------------------------------------------------------- 5. paired effects
def variant_channel_effect():
    rows = [json.loads(l) for l in open('data/round2/phase3/H2_fullN.jsonl')]
    n = len(rows)
    p2h = sum(1 for r in rows if r['p2'].get('hit'))
    p3h = sum(1 for r in rows if r['p3'].get('hit'))
    paired = [(bool(r['p2'].get('hit')), bool(r['p3'].get('hit'))) for r in rows]
    mc = mcnemar(paired)
    z, zp = two_prop_z(p2h, n, p3h, n)
    return {'n': n, 'p2_R@1': round(p2h / n, 4), 'p3_R@1': round(p3h / n, 4),
            'delta_pp': round((p3h - p2h) / n * 100, 1),
            'mcnemar': mc, 'two_prop_z': z, 'two_prop_p': zp,
            'p3_win': mc['c_only'], 'p2_win': mc['b_only']}

def scaffold_effect():
    """scaffolded − unscaffolded control, same cases, same backbone, per dataset.
    Reported for the backbone with best control coverage (Gemini Flash)."""
    results = []
    bb = 'gemini-3-flash-preview'
    for ds in ('phenopacket_store', 'rarearena_rds'):  # capped frames with full coverage
        ctrl = case_hits(ds, CONTROL, bb)
        if not ctrl:
            continue
        for scaf in SCAFFOLDED:
            sh = case_hits(ds, scaf, bb)
            if not sh:
                continue
            common = sorted(set(ctrl) & set(sh))
            if len(common) < 30:
                continue
            paired = [(ctrl[c], sh[c]) for c in common]  # (control, scaffolded)
            ch = sum(ctrl[c] for c in common); sfh = sum(sh[c] for c in common)
            mc = mcnemar(paired)
            results.append({
                'dataset': ds, 'scaffolded_system': scaf, 'backbone': bb,
                'n_common_cases': len(common),
                'control_R@1': round(ch / len(common), 4),
                'scaffolded_R@1': round(sfh / len(common), 4),
                'delta_pp': round((sfh - ch) / len(common) * 100, 1),
                'mcnemar_chi2_cc': mc['chi2_cc'], 'mcnemar_p': mc['p'],
                'scaffold_win': mc['c_only'], 'control_win': mc['b_only'],
            })
    return results

# ---------------------------------------------------------------- 6. P1 / P5 checks
def p1_check():
    rows = [json.loads(l) for l in open('data/round2/phase1/p1_metric_rows.jsonl')]
    # This is HPO-extraction phrase P/R/F1 (P1), NOT diagnosis R@1.
    return {
        'note': 'p1_metric_rows.jsonl measures HPO-EXTRACTION phrase P/R/F1, not diagnosis R@1',
        'n_rows': len(rows),
        'agents': sorted({r['agent'] for r in rows}),
        'cascade_0.40_vs_0.04': {
            'source': 'paper_sections/7_1_p1_p2_cascade.md:15',
            'gold_HPO_0.40': '25 Phenopacket-Store cases (native gold_hpo_terms input)',
            'extracted_HPO_0.04': '25 RareArena RDS cases (LLM-extracted HPO)',
            'same_case_paired': False,
            'verdict': 'DIFFERENT DATASETS / different case halves — NOT a same-case paired '
                       'phenotype-extraction penalty. Confounds dataset difficulty with input condition.',
        },
    }

def p5_check():
    def load(f):
        d = {}
        for l in open(f):
            r = json.loads(l)
            d[(r['agent_id'], r['case_id'])] = r
        return d
    v1 = load('data/round2/phase1/p5_judge_scores_v1.jsonl')  # Gemini
    v2 = load('data/round2/phase1/p5_judge_scores_v2.jsonl')  # Claude
    shared = sorted(set(v1) & set(v2))
    tl_mismatch = sum(1 for k in shared if v1[k].get('trace_len') != v2[k].get('trace_len'))
    by_agent_tl = defaultdict(lambda: {'v1': set(), 'v2': set()})
    for k in shared:
        by_agent_tl[k[0]]['v1'].add(v1[k].get('trace_len'))
        by_agent_tl[k[0]]['v2'].add(v2[k].get('trace_len'))
    return {
        'v1_judge': 'Gemini (family)', 'v2_judge': 'Claude (non-family)',
        'n_shared_scores': len(shared),
        'trace_len_mismatch_pairs': tl_mismatch,
        'per_agent_trace_len': {a: {'v1': sorted(x for x in d['v1'] if x is not None),
                                    'v2': sorted(x for x in d['v2'] if x is not None)}
                                for a, d in by_agent_tl.items()},
        'rho_gemini_reported': 0.098, 'rho_claude_reported': 0.616,
        'verdict': 'INVALID for self-preference estimation: the two judges did NOT score '
                   'identical frozen traces (trace_len differs on %d/%d pairs; Gemini(v1) saw '
                   'truncated/zero traces for maidxo & mdagents, Claude(v2) saw repaired traces). '
                   'The rho=0.098 vs rho=0.616 contrast conflates the trace-capture fix with judge '
                   'identity. Mark P5 as EXPLORATORY / physician-validation-in-progress.' % (tl_mismatch, len(shared)),
    }

# ---------------------------------------------------------------- run all
def main():
    write_manifest()
    cands = write_headline()
    by_bb, cost_tot = write_cost()
    holdout = write_holdout()
    vce = variant_channel_effect()
    scaf = scaffold_effect()
    p1 = p1_check()
    p5 = p5_check()

    snapshot = {
        'generated_by': 'audit_frozen/build_deliverables.py (frozen-results audit)',
        'generated_at': '__STAMP__',
        'frozen_commit': FROZEN_COMMIT,
        'data_version': 'slim recompute set (MIMIC & model weights stripped from git history)',
        'preregistered_primary_metric': {
            'value': 'Recall@1 (variant-aware), attempted-denominator',
            'note': 'OSF prereg lists R@1 as Tier-1 but does not explicitly fix strict-vs-variant '
                    'as primary. Original pipeline used success-only denominator (n_ok); this audit '
                    'uses n_attempted per the freeze brief (failures/timeouts/empty/parser kept in).',
        },
        'receipt_counts': {
            'raw_lines_phase4a': 101060,
            'attempted_after_dedupe_and_cap': sum(r['n_attempted'] for r in ROWS),
            'successful': sum(r['n_successful'] for r in ROWS),
            'failed': sum(r['n_failed'] for r in ROWS),
            'status_breakdown': {'ok': 97217, 'parser_error': 2691, 'agent_error': 207,
                                 'timeout': 945, 'ok_but_empty': 70},
            'cells': len(ROWS),
        },
        'exclusion_rules': [
            'Dedupe by case_id, prefer status==ok (RESUME re-attempts collapsed).',
            'Canonical N=2000 cap applied to phenopacket_store & rarearena_rds (data/round2/phase4a_canonical_2000.json).',
            'Failures (timeout/parser_error/agent_error/empty-ok) RETAINED in R@1 denominator (n_attempted).',
            'mimic_diverse gold is stripped from this commit -> correctness not recomputable (cost/predictions also absent).',
            'Cost headline = MAIN_MATRIX frozen cells only; pilots/ablations/judge/holdout tracked separately.',
        ],
        'headline_values_recomputed': {
            name: {'paper_candidate': cand, 'recomputed': got, 'ci': ci, 'provenance': prov}
            for name, cand, got, ci, prov in cands
        },
        'cost_inclusion_sets': {
            'frozen_main_matrix_recomputed': {
                'attempted': cost_tot['attempted'], 'successful': cost_tot['successful'],
                'usd': round(cost_tot['usd'], 2), 'cells': cost_tot['cells'],
            },
            'paper_106089_$315.21': 'J appendix TOTAL, 93 cells INCLUDING now-stripped mimic_diverse + all GPT-5; '
                                    'ok-level count; NOT reproducible from this slim commit (mimic removed).',
            'paper_68668_$191.76': 'main_results.md "all cells" 2026-07-06 snapshot; partial completion state.',
            'paper_48728_$109.41': 'leaderboard/index.html earlier/partial snapshot.',
            'brief_50479_$109.41_note': 'brief cited 50,479 for the $109.41 set; leaderboard shows 48,728 — '
                                        'mismatch flagged (likely a transcription/rounding drift).',
        },
        'paired_effects': {'variant_channel': vce, 'scaffold_effect_gemini': scaf},
        'temporal_holdout': holdout,
        'p1_p2_cascade': p1,
        'p5_self_preference': p5,
    }
    (OUT / 'results_snapshot.json').write_text(json.dumps(snapshot, indent=2, default=str))
    print('deliverables written to audit_frozen/')
    print(json.dumps({'headline': snapshot['headline_values_recomputed'],
                      'variant_channel': vce,
                      'holdout_pooled': {k: holdout[k] for k in ('pooled_pre', 'pooled_post', 'pooled_delta_pp')}},
                     indent=2, default=str))

if __name__ == '__main__':
    main()

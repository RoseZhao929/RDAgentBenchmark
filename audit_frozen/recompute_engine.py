"""Frozen-results audit — recompute engine.

Rebuilds the frozen main matrix from case-level receipts, recomputing every
headline number from scratch. Deliberately DIVERGES from the original
scripts/phase4a_report_gen.py in one load-bearing way:

  ORIGINAL:  R@1 = hits / n_ok            (success-only denominator)
  AUDIT:     R@1 = hits / n_attempted     (failures/timeouts/empty/parser
                                           errors stay in the denominator)

Both are emitted so the delta is auditable. The audit primary is the
attempted-denominator metric, per the freeze brief.

Matching policy is reused verbatim from harness.metrics.cross_map
(gold_hit_with_crossmap / gold_hit_with_variants) so we do not silently
change the scoring semantics.
"""
from __future__ import annotations
import sys, json, os, glob, math
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from harness.canonical_case import CanonicalCase  # noqa: E402
# repo ships a hardcoded macOS absolute path for the Orphadata XML; rebind the
# parse_orphadata default to the in-repo copy so the crossmap loader works here.
import harness.pmc_oa.orphanet as _orph  # noqa: E402
_LOCAL_ORPHA = str(REPO / 'data' / 'orphadata' / 'en_product1.xml')
_orph.DEFAULT_ORPHA_XML = _LOCAL_ORPHA
_orph.parse_orphadata.__defaults__ = (_LOCAL_ORPHA,)
import harness.metrics.cross_map as _cm  # noqa: E402
# REPO BUG: _fuzzy_name_to_orpha's docstring promises an lru_cache but the
# decorator is missing, so rapidfuzz rescans ~26K Orphanet names for EVERY
# prediction via fuzz.WRatio (aggregation takes hours). We precompute the
# name->ORPHA map ONCE with a batched, multithreaded rapidfuzz.process.cdist
# pass (audit_frozen/precompute_fuzzy.py) reproducing map_diagnosis semantics
# exactly, then serve it here as an O(1) lookup. The normalization key matches
# harness.pmc_oa.orphanet._normalize so results are identical.
from harness.pmc_oa.orphanet import _normalize as _norm  # noqa: E402
_FUZZY_MAP_PATH = REPO / 'audit_frozen' / '_fuzzy_name_map.json'
if _FUZZY_MAP_PATH.exists():
    _RAW = json.loads(_FUZZY_MAP_PATH.read_text())
    # index by normalized form (map_diagnosis normalizes before matching)
    _FUZZY = {}
    for _k, _v in _RAW.items():
        _FUZZY.setdefault(_norm(_k), _v)
    def _fuzzy_cached(pid):
        return _FUZZY.get(_norm(pid))
    _cm._fuzzy_name_to_orpha = _fuzzy_cached
else:
    from functools import lru_cache as _lru  # noqa: E402
    _cm._fuzzy_name_to_orpha = _lru(maxsize=None)(_cm._fuzzy_name_to_orpha)
from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants  # noqa: E402
from harness.ingest import ingest_phenopacket_store, ingest_rarearena, ingest_rarebench  # noqa: E402

FROZEN_COMMIT = "43efa1e516fffeac22786251656891109e40309a"
CANON_PATH = "data/round2/phase4a_canonical_2000.json"

# ---------------------------------------------------------------- gold loading
def load_gold():
    """case_id -> (dataset_tag, GoldLabel). Returns (gold, provenance)."""
    gold = {}
    prov = {}
    def add(cases, tag, n_source):
        n = 0
        for c in cases:
            gold[c.case_id] = (tag, c.gold_label)
            n += 1
        prov[tag] = {"n_gold_cases": n, "n_source_rows": n_source}

    add(ingest_phenopacket_store('data/phenopacket_store/notebooks'),
        'phenopacket_store', None)
    add(ingest_rarearena('data/rarearena/benchmark_data/RDS_benchmark.jsonl', 'RDS'),
        'rarearena_rds', 8562)
    rb = []
    for split in ('RAMEDIS', 'LIRICAL', 'MME', 'HMS'):
        rb += list(ingest_rarebench(f'data/rarebench_hf/data_unzipped/data/{split}.jsonl', split))
    add(rb, 'rarebench', 624 + 370 + 40 + 88)

    # temporal holdout gold (pre/post cutoff) — CanonicalCase jsonl
    for tag, path in (('pmc_oa_holdout', 'data/pmc_oa_holdout/holdout_gold_opus.jsonl'),
                      ('pmc_precutoff', 'data/pmc_precutoff/holdout_gold_opus.jsonl')):
        n = 0
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if not line:
                    continue
                c = CanonicalCase.model_validate_json(line)
                gold[c.case_id] = (tag, c.gold_label)
                n += 1
        prov[tag] = {"n_gold_cases": n, "n_source_rows": n}

    # MIMIC gold is intentionally stripped from this slim recompute set.
    prov['mimic_diverse'] = {"n_gold_cases": 0, "n_source_rows": None,
                             "note": "gold stripped from slim recompute commit; not recomputable"}
    return gold, prov

# ---------------------------------------------------------------- file parsing
DATASETS = ('phenopacket_store', 'rarearena_rds', 'rarebench', 'mimic_diverse',
            'pmc_oa_holdout', 'pmc_precutoff')
AGENTS = ('mdagents', 'medagents', 'agentclinic', 'maidxo', 'deeprare',
          'llm_control', 'vc_rdagent', 'lirical')

def parse_filename(fn):
    for d in DATASETS:
        if fn.startswith(d + '_'):
            rest = fn[len(d) + 1:]
            for a in AGENTS:
                if rest.startswith(a + '_'):
                    return d, a, rest[len(a) + 1:]
            return d, None, None
    return None, None, None

def dedupe_cases(path):
    """One record per case_id, preferring ok (matches original dedupe)."""
    best = {}
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        cid = r.get('case_id')
        if cid is None:
            continue
        prev = best.get(cid)
        if prev is None or (r.get('status') == 'ok' and prev.get('status') != 'ok'):
            best[cid] = r
        elif prev.get('status') != 'ok':
            best[cid] = r
    return best

def is_success(r):
    """Success = status ok AND non-empty predictions. Empty-ok is a failure."""
    return r.get('status') == 'ok' and bool(r.get('ranked_predictions'))

def api_calls_of(r):
    """Best-effort per-receipt api-call count from agent-specific extra keys."""
    ex = r.get('extra') or {}
    for k in ('medagents_n_calls', 'agentclinic_n_inferences', 'maidxo_iterations_used'):
        if isinstance(ex.get(k), (int, float)):
            return int(ex[k])
    # off-wrapper classical tools make 0 LLM calls
    if (r.get('cost') or {}).get('provider') is None:
        return 0
    return 1  # default: one synthesis call

# ---------------------------------------------------------------- bootstrap
def bootstrap_ci_cases(hit_flags, n_boot=5000, seed=42):
    """True case-level percentile bootstrap over a 0/1 vector of length
    n_attempted (failures included as 0). Returns (lo, hi) for the mean.

    Vectorised: resampling a 0/1 vector of size n with replacement and taking
    the mean is equivalent to drawing Binomial(n, p)/n, where p is the observed
    hit rate. This is exact for the mean statistic and avoids a 900M-iteration
    Python loop.
    """
    import numpy as np
    n = len(hit_flags)
    if n == 0:
        return (0.0, 0.0)
    p = sum(hit_flags) / n
    rng = np.random.default_rng(seed)
    rates = rng.binomial(n, p, size=n_boot) / n
    lo, hi = np.percentile(rates, [2.5, 97.5])
    return (round(float(lo), 4), round(float(hi), 4))

# ---------------------------------------------------------------- main
def build_manifest():
    gold, prov = load_gold()
    canon = {}
    if os.path.exists(CANON_PATH):
        canon = {k: set(v) for k, v in json.load(open(CANON_PATH)).items()}

    cells = {}
    for p in sorted(glob.glob('data/round2/phase4a/predictions_*.jsonl')):
        fn = os.path.basename(p).replace('predictions_', '').replace('.jsonl', '')
        ds, ag, bb = parse_filename(fn)
        if not ds or not ag:
            continue
        best = dedupe_cases(p)
        # canonical N=2000 cap for pp/rarearena (frozen sampling frame)
        capped = ds in canon
        if capped:
            best = {cid: r for cid, r in best.items() if cid in canon[ds]}

        key = (ds, ag, bb[:30])
        c = cells.setdefault(key, {
            'dataset': ds, 'agent': ag, 'backbone': bb[:30],
            'n_attempted': 0, 'n_successful': 0, 'n_failed': 0,
            'fail_timeout': 0, 'fail_parser': 0, 'fail_agent': 0, 'fail_empty_ok': 0,
            'h1s': 0, 'h1v': 0, 'h5s': 0, 'h5v': 0,
            'sum_usd': 0.0, 'sum_lat_ms': 0, 'api_calls': 0,
            'no_gold': 0, 'capped_frame': capped,
            '_hit1s_flags': [], '_hit1v_flags': [],
        })
        for r in best.values():
            c['n_attempted'] += 1
            c['api_calls'] += api_calls_of(r)
            c['sum_usd'] += (r.get('cost') or {}).get('cost_usd', 0) or 0
            c['sum_lat_ms'] += r.get('total_latency_ms', 0) or 0
            st = r.get('status', '?')
            succ = is_success(r)
            if not succ:
                c['n_failed'] += 1
                if st == 'timeout':
                    c['fail_timeout'] += 1
                elif st == 'parser_error':
                    c['fail_parser'] += 1
                elif st == 'agent_error':
                    c['fail_agent'] += 1
                elif st == 'ok':
                    c['fail_empty_ok'] += 1
                # failed => counts as 0 in the attempted-denominator metric
                c['_hit1s_flags'].append(0)
                c['_hit1v_flags'].append(0)
                continue
            c['n_successful'] += 1
            _, g = gold.get(r['case_id'], (None, None))
            if not g:
                c['no_gold'] += 1
                c['_hit1s_flags'].append(0)
                c['_hit1v_flags'].append(0)
                continue
            preds = r.get('ranked_predictions', [])
            variants = (r.get('extra') or {}).get('ranked_predictions_variants') or []
            h1s = bool(preds and gold_hit_with_crossmap(preds[0], g))
            h5s = any(gold_hit_with_crossmap(x, g) for x in preds[:5])
            if variants:
                h1v = gold_hit_with_variants(variants[0], g)
                h5v = any(gold_hit_with_variants(v, g) for v in variants[:5])
            else:
                h1v, h5v = h1s, h5s
            c['h1s'] += h1s; c['h5s'] += h5s; c['h1v'] += h1v; c['h5v'] += h5v
            c['_hit1s_flags'].append(1 if h1s else 0)
            c['_hit1v_flags'].append(1 if h1v else 0)

    return cells, prov, canon

def finalize(cells):
    """Compute derived metrics (both denominators) + bootstrap CI."""
    rows = []
    for key, c in sorted(cells.items()):
        na = c['n_attempted']; ns = c['n_successful']
        def rate(h, d):
            return round(h / d, 4) if d else None
        ci_attempt = bootstrap_ci_cases(c['_hit1v_flags'])
        row = {
            'dataset': c['dataset'], 'system': c['agent'], 'backbone': c['backbone'],
            'capability': 'P2_phenotype_ddx', 'evaluation_pass': 'gold_hpo',
            'n_planned': na,  # frozen frame == attempted after cap+dedupe
            'n_attempted': na, 'n_successful': ns, 'n_failed': c['n_failed'],
            'fail_timeout': c['fail_timeout'], 'fail_parser': c['fail_parser'],
            'fail_agent': c['fail_agent'], 'fail_empty_ok': c['fail_empty_ok'],
            'no_gold': c['no_gold'],
            # AUDIT PRIMARY: attempted-denominator (failures kept in)
            'top1_correct_strict': c['h1s'],
            'top1_correct_variant_aware': c['h1v'],
            'R@1_strict': rate(c['h1s'], na),
            'R@1_variant_aware': rate(c['h1v'], na),
            'R@5_strict': rate(c['h5s'], na),
            'R@5_variant_aware': rate(c['h5v'], na),
            'R@5': rate(c['h5v'], na),
            'bootstrap_95CI': f"[{ci_attempt[0]}, {ci_attempt[1]}]",
            # ORIGINAL-STYLE: success-only denominator (for delta comparison)
            'R@1_variant_success_denom': rate(c['h1v'], ns),
            'R@1_strict_success_denom': rate(c['h1s'], ns),
            'api_calls': c['api_calls'],
            'total_cost_usd': round(c['sum_usd'], 6),
            'cost_per_attempt': round(c['sum_usd'] / na, 6) if na else None,
            'cost_per_success': round(c['sum_usd'] / c['h1v'], 6) if c['h1v'] else None,
            'latency_per_attempt_ms': round(c['sum_lat_ms'] / na, 1) if na else None,
            'capped_frame': c['capped_frame'],
        }
        rows.append(row)
    return rows

if __name__ == '__main__':
    cells, prov, canon = build_manifest()
    rows = finalize(cells)
    Path('audit_frozen/_gold_provenance.json').write_text(json.dumps(prov, indent=2))
    Path('audit_frozen/_manifest_rows.json').write_text(json.dumps(rows, indent=2))
    print(f"cells={len(rows)}  gold_datasets={list(prov)}")
    print(f"total attempted={sum(r['n_attempted'] for r in rows)}  "
          f"successful={sum(r['n_successful'] for r in rows)}  "
          f"failed={sum(r['n_failed'] for r in rows)}")

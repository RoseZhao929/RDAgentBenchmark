"""Precompute name->ORPHA fuzzy map for every unique plain-text prediction.

Reproduces harness.pmc_oa.orphanet.map_diagnosis semantics exactly
(_normalize -> exact name_to_orpha lookup -> else fuzz.WRatio >= 90), but
batches the fuzzy step with rapidfuzz.process.cdist (multithreaded, GIL-free)
instead of 51K separate process.extract calls. Result cached to JSON so the
recompute engine loads it in O(1).
"""
from __future__ import annotations
import sys, json, glob, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import os; os.chdir(REPO)

import harness.pmc_oa.orphanet as o
_LOCAL = str(REPO / 'data' / 'orphadata' / 'en_product1.xml')
o.DEFAULT_ORPHA_XML = _LOCAL
o.parse_orphadata.__defaults__ = (_LOCAL,)
from harness.pmc_oa.orphanet import _normalize  # noqa: E402
from rapidfuzz import process, fuzz  # noqa: E402

FUZZY_THRESHOLD = 90

def collect_names():
    names = set()
    for p in glob.glob('data/round2/phase4a/predictions_*.jsonl'):
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('status') != 'ok':
                continue
            preds = (r.get('ranked_predictions') or [])[:5]
            variants = ((r.get('extra') or {}).get('ranked_predictions_variants') or [])[:5]
            flat = list(preds)
            for v in variants:
                flat += (v if isinstance(v, list) else [v])
            for x in flat:
                if isinstance(x, str) and x and not x.startswith(('OMIM:', 'ORPHA:', 'CCRD:', 'HP:')):
                    names.add(x.strip())
    return sorted(names)

def main():
    t0 = time.time()
    tables = o.parse_orphadata()
    name_to_orpha = tables['name_to_orpha']
    choices = list(name_to_orpha.keys())
    print(f'parsed orphadata: {len(choices)} names, {round(time.time()-t0,1)}s', file=sys.stderr)

    raw_names = collect_names()
    print(f'unique plain-text predictions: {len(raw_names)}', file=sys.stderr)

    # normalized query per raw name; exact hits resolved directly
    result = {}          # raw_name -> orpha_id or None
    fuzzy_queries = []   # normalized strings needing fuzzy
    fuzzy_raw = []       # parallel raw names
    seen_norm = {}
    for rn in raw_names:
        norm = _normalize(rn)
        if norm in name_to_orpha:
            result[rn] = name_to_orpha[norm]
        else:
            fuzzy_queries.append(norm)
            fuzzy_raw.append(rn)
    print(f'exact hits: {len(result)}  fuzzy needed: {len(fuzzy_queries)}', file=sys.stderr)

    # batched cdist in chunks (keeps memory bounded: chunk x 26365 float32)
    t1 = time.time()
    CHUNK = 2000
    import numpy as np
    for i in range(0, len(fuzzy_queries), CHUNK):
        qs = fuzzy_queries[i:i+CHUNK]
        rns = fuzzy_raw[i:i+CHUNK]
        m = process.cdist(qs, choices, scorer=fuzz.WRatio, workers=-1)
        best_idx = np.argmax(m, axis=1)
        best_score = m[np.arange(len(qs)), best_idx]
        for j, rn in enumerate(rns):
            if best_score[j] >= FUZZY_THRESHOLD:
                result[rn] = name_to_orpha[choices[best_idx[j]]]
            else:
                result[rn] = None
        print(f'  fuzzy {i+len(qs)}/{len(fuzzy_queries)}  '
              f'({round(time.time()-t1,1)}s)', file=sys.stderr)

    out = Path('audit_frozen/_fuzzy_name_map.json')
    out.write_text(json.dumps(result))
    n_hit = sum(1 for v in result.values() if v)
    print(f'wrote {out}: {len(result)} names, {n_hit} mapped, '
          f'total {round(time.time()-t0,1)}s')

if __name__ == '__main__':
    main()

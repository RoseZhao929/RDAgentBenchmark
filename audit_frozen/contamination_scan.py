"""补2 — temporal holdout contamination / overlap 去重扫描.

确认 temporal holdout (pmc_oa_holdout + pmc_precutoff) 是否与各 development
层 (RareArena RDS / Phenopacket-Store / RareBench) 重叠。两路证据:

  A. 精确 ID 交集:
     - PMCID: holdout case_id `pmc_<PMCID>` vs RareArena `_id` 前缀 (也是 PMCID)
     - PMID:  holdout 02_pmid_to_pmc.jsonl 的 pmid vs Phenopacket case_id `PMID_<pmid>_...`
  B. 文本近重复 (vignette word-shingle Jaccard, 倒排加速):
     holdout free_text_vignette vs RareArena case_report
     (二者都是 PMC case-report free text — 最可能撞车的一对)

只报告事实交集,不下 "无 memorization" 的结论。
"""
from __future__ import annotations
import sys, json, re, os
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO)); os.chdir(REPO)
import harness.pmc_oa.orphanet as _o
_L = str(REPO / 'data' / 'orphadata' / 'en_product1.xml')
_o.DEFAULT_ORPHA_XML = _L; _o.parse_orphadata.__defaults__ = (_L,)
from harness.ingest import ingest_phenopacket_store, ingest_rarearena  # noqa: E402

OUT = REPO / 'audit_frozen'

# ---------------------------------------------------------------- collect ids
def holdout_ids():
    """Return dict: split -> {pmcids:set, pmids:set, cases:[(case_id,vignette)]}."""
    res = {}
    for split, gp, mp in (
        ('post_cutoff', 'data/pmc_oa_holdout/holdout_gold_opus.jsonl',
         'data/pmc_oa_holdout/02_pmid_to_pmc.jsonl'),
        ('pre_cutoff', 'data/pmc_precutoff/holdout_gold_opus.jsonl',
         'data/pmc_precutoff/02_pmid_to_pmc.jsonl'),
    ):
        pmcids, cases = set(), []
        for line in open(gp):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            cid = r['case_id']  # pmc_<PMCID>
            m = re.match(r'pmc_?(\d+)', cid)
            if m:
                pmcids.add(m.group(1))
            cases.append((cid, r.get('free_text_vignette') or ''))
        # pmid set from pmid->pmc map, restricted to holdout pmcids
        pmids = set()
        pmc2pmid = {}
        if os.path.exists(mp):
            for line in open(mp):
                d = json.loads(line)
                pmc = str(d.get('pmc_id', '')).replace('PMC', '').lstrip('pmc_')
                pmid = str(d.get('pmid', ''))
                if pmc:
                    pmc2pmid[pmc] = pmid
        for pmc in pmcids:
            if pmc in pmc2pmid:
                pmids.add(pmc2pmid[pmc])
        res[split] = {'pmcids': pmcids, 'pmids': pmids, 'cases': cases}
    return res

def rarearena_index():
    """RareArena _id 前缀 = PMCID. Return (pmcid_set, [(pmcid, case_report)])."""
    pmcids, docs = set(), []
    for c_raw in open('data/rarearena/benchmark_data/RDS_benchmark.jsonl'):
        r = json.loads(c_raw)
        _id = str(r['_id'])
        pmc = _id.split('-')[0]
        pmcids.add(pmc)
        docs.append((pmc, r.get('case_report') or ''))
    return pmcids, docs

def phenopacket_pmids():
    pmids = set()
    for c in ingest_phenopacket_store('data/phenopacket_store/notebooks'):
        m = re.match(r'PMID_(\d+)', c.case_id)
        if m:
            pmids.add(m.group(1))
    return pmids

# ---------------------------------------------------------------- near-dup
_WORD = re.compile(r'[a-z]+')

def shingles(text, k=5):
    toks = _WORD.findall(text.lower())
    if len(toks) < k:
        return set()
    return {hash(tuple(toks[i:i + k])) for i in range(len(toks) - k + 1)}

def build_inverted(docs, k=5):
    """shingle_hash -> set(doc_idx). Also return per-doc shingle sets."""
    inv = defaultdict(set)
    sh = []
    for i, (_id, text) in enumerate(docs):
        s = shingles(text, k)
        sh.append(s)
        for h in s:
            inv[h].add(i)
    return inv, sh

def near_dup(holdout_cases, dev_docs, k=5, thresh=0.5):
    """For each holdout vignette, find best-Jaccard RareArena doc via inverted
    index on shared shingles. Report pairs with Jaccard >= thresh."""
    inv, dev_sh = build_inverted(dev_docs, k)
    hits = []
    for cid, vig in holdout_cases:
        hs = shingles(vig, k)
        if not hs:
            continue
        cand = defaultdict(int)
        for h in hs:
            for di in inv.get(h, ()):
                cand[di] += 1
        best_j, best_di = 0.0, None
        for di, shared in cand.items():
            union = len(hs) + len(dev_sh[di]) - shared
            j = shared / union if union else 0.0
            if j > best_j:
                best_j, best_di = j, di
        if best_di is not None and best_j >= thresh:
            hits.append({'holdout_case': cid, 'rarearena_pmcid': dev_docs[best_di][0],
                         'jaccard': round(best_j, 3)})
    return hits

# ---------------------------------------------------------------- run
def main():
    ho = holdout_ids()
    ra_pmc, ra_docs = rarearena_index()
    pp_pmid = phenopacket_pmids()

    report = {'exact_id_overlap': {}, 'near_duplicate': {}, 'summary': {}}
    for split, d in ho.items():
        pmc_ovl = sorted(d['pmcids'] & ra_pmc)
        pmid_ovl = sorted(d['pmids'] & pp_pmid)
        report['exact_id_overlap'][split] = {
            'n_holdout_pmcids': len(d['pmcids']),
            'n_holdout_pmids_resolved': len(d['pmids']),
            'pmcid_overlap_with_rarearena': pmc_ovl,
            'n_pmcid_overlap': len(pmc_ovl),
            'pmid_overlap_with_phenopacket': pmid_ovl,
            'n_pmid_overlap': len(pmid_ovl),
        }
        nd = near_dup(d['cases'], ra_docs, k=5, thresh=0.4)
        report['near_duplicate'][split] = {
            'threshold_jaccard': 0.4, 'shingle_k': 5,
            'n_holdout_cases': len(d['cases']),
            'n_near_dup_vs_rarearena': len(nd),
            'pairs': nd[:50],
        }

    report['summary'] = {
        'rarearena_indexed': len(ra_docs),
        'phenopacket_pmids': len(pp_pmid),
        'method': 'exact PMCID/PMID set intersection + word-5-shingle Jaccard (inverted index)',
        'caveat': 'RareBench/Phenopacket lack free-text vignettes so text near-dup only run vs '
                  'RareArena (the only free-text dev layer). Exact ID intersection covers all layers '
                  'where an ID is available. Absence of overlap here does NOT by itself prove no '
                  'contamination — LLM pretraining exposure is out of scope.',
    }
    (OUT / '_contamination_scan.json').write_text(json.dumps(report, indent=2))
    for split in ho:
        e = report['exact_id_overlap'][split]
        n = report['near_duplicate'][split]
        print(f"[{split}] pmcid_overlap={e['n_pmcid_overlap']} "
              f"pmid_overlap={e['n_pmid_overlap']} "
              f"near_dup(J>=0.4)={n['n_near_dup_vs_rarearena']}/{n['n_holdout_cases']}")

if __name__ == '__main__':
    main()

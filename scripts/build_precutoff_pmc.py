"""Build a PRE-cutoff PMC-OA rare-disease case-report set, matched to the
post-cutoff holdout by using the identical pipeline + MeSH query, only changing
the publication-date window to 2016-2020 (well inside every backbone's training
window). This is the difficulty-controlled contamination reference for H3:

    same source (PMC OA case reports), same extraction pipeline (Gemini 3 Flash),
    same Orphanet mapping, same query — only "was it in training?" differs.

Pre-cutoff R@1 ≈ post-cutoff R@1  =>  no memorisation inflation.
Pre-cutoff R@1 >> post-cutoff R@1  =>  contamination inflated the pre-cutoff.

Stages (resumable): search -> link -> fetch -> extract -> orpha-map -> finalize.
Output dir: data/pmc_precutoff/
"""
from __future__ import annotations
import json, os, sys, time, gzip
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agents._adapter_utils import load_dotenv
load_dotenv()
os.environ.setdefault("CANARY_BACKBONE_MODEL", "google/gemini-3-flash-preview-20251217")
from harness.pmc_oa import search, linking, fetch, extract, orphanet

OUT = ROOT / "data/pmc_precutoff"
OUT.mkdir(parents=True, exist_ok=True)
XML_DIR = OUT / "xml"; XML_DIR.mkdir(exist_ok=True)
KEY = os.environ.get("NCBI_API_KEY") or os.environ.get("OPENROUTER_API_KEY_UNUSED")  # NCBI optional
TARGET = 250          # final matched cases wanted
MAX_PMIDS = 1500      # search ceiling


def stage_search():
    f = OUT / "01_pmids.jsonl"
    if f.exists() and sum(1 for _ in open(f)) > 0:
        print(f"[search] exists ({sum(1 for _ in open(f))})"); return
    n = 0
    with f.open("w") as out:
        for pmid in search.search_pubmed_pmids(cutoff_date="2016/01/01",
                                                end_date="2020/12/31"):
            out.write(json.dumps({"pmid": pmid}) + "\n"); n += 1
            if n >= MAX_PMIDS:
                break
    print(f"[search] {n} pre-cutoff PMIDs")


def stage_link():
    f = OUT / "02_pmid_to_pmc.jsonl"
    if f.exists() and sum(1 for _ in open(f)) > 0:
        print(f"[link] exists ({sum(1 for _ in open(f))})"); return
    pmids = [json.loads(l)["pmid"] for l in open(OUT / "01_pmids.jsonl")]
    mapping = {}
    for i in range(0, len(pmids), 180):
        batch = pmids[i:i+180]
        try:
            mapping.update(linking.pmid_to_pmc_batch(batch))
        except Exception as e:
            print(f"  link batch {i} err {e}")
        time.sleep(0.34)
        if len(mapping) >= TARGET * 3:
            break
    with f.open("w") as out:
        for pmid, pmc in mapping.items():
            out.write(json.dumps({"pmid": pmid, "pmc_id": pmc}) + "\n")
    print(f"[link] {len(mapping)} PMID->PMC")


def stage_fetch():
    recs = [json.loads(l) for l in open(OUT / "02_pmid_to_pmc.jsonl")]
    got = 0
    for r in recs:
        pmc = r["pmc_id"].replace("PMC", "")
        dest = XML_DIR / f"PMC{pmc}.xml.gz"
        if dest.exists():
            got += 1; continue
        if got >= TARGET * 2:
            break
        try:
            xml = fetch.fetch_xml(pmc)
            with gzip.open(dest, "wb") as w:
                w.write(xml if isinstance(xml, bytes) else xml.encode())
            got += 1
            if got % 50 == 0:
                print(f"[fetch] {got}", flush=True)
            time.sleep(0.34)
        except Exception as e:
            print(f"  fetch PMC{pmc} err {e}")
    print(f"[fetch] {got} XMLs in {XML_DIR}")


def stage_extract():
    out = OUT / "04_extracted.jsonl"
    stats = extract.batch_extract_from_dir(
        XML_DIR, out,
        model="google/gemini-3-flash-preview-20251217",
        limit=TARGET * 2, skip_existing=True)
    print(f"[extract] {stats}")


def stage_map():
    out = OUT / "05_orphanet_mapped.jsonl"
    if out.exists() and sum(1 for _ in open(out)) > 0:
        print(f"[map] exists ({sum(1 for _ in open(out))})"); return
    orphanet.batch_map_extracted(OUT / "04_extracted.jsonl", out)
    print(f"[map] done -> {out}")


def stage_finalize():
    # join 05 (orpha map) with 04 (extraction: hpo + excerpt) by pmc_id
    ext = {}
    for l in open(OUT / "04_extracted.jsonl"):
        r = json.loads(l); ext[str(r.get("pmc_id"))] = r
    cand = []
    for l in open(OUT / "05_orphanet_mapped.jsonl"):
        m = json.loads(l)
        pid = str(m.get("pmc_id"))
        e = ext.get(pid, {})
        orpha = m.get("orpha_id") or (m.get("top_candidates") or [{}])[0].get("orpha_id")
        hpo = e.get("hpo_phenotypes") or []
        if orpha and len(hpo) >= 3 and e.get("case_excerpt"):
            cand.append({
                "pmc_id": pid,
                "orpha_id": orpha,
                "omim_ids": m.get("omim_ids") or [],
                "matched_orpha_name": m.get("matched_name"),
                "extracted_diagnosis": e.get("final_diagnosis") or m.get("extracted_diagnosis"),
                "match_type": m.get("match_type"),
                "match_score": m.get("score"),
                "hpo_phenotypes": hpo,
                "age_at_presentation_years": e.get("age_at_presentation_years"),
                "sex": e.get("sex"),
                "case_excerpt": e.get("case_excerpt"),
                "pub_year_in_text": e.get("pub_year_in_text"),
                "top_candidates": m.get("top_candidates"),
            })
    cand = cand[:TARGET]
    fp = OUT / "06_candidates.jsonl"
    with fp.open("w") as out:
        for r in cand:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[finalize] {len(cand)} pre-cutoff candidates -> {fp}")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"search": stage_search, "link": stage_link, "fetch": stage_fetch,
             "extract": stage_extract, "map": stage_map, "finalize": stage_finalize}
    if stage == "all":
        for s in ["search", "link", "fetch", "extract", "map", "finalize"]:
            print(f"=== {s} ===", flush=True); steps[s]()
    else:
        steps[stage]()

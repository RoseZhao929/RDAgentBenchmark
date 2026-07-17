"""Step 1: E-utils esearch for candidate PMC OA case reports.

NCBI Entrez API: https://www.ncbi.nlm.nih.gov/books/NBK25501/

Discovery (2026-05-11): PMC db esearch with `"open access"[filter]` returns
only ~100 hits for "Rare Diseases"[MeSH] — far fewer than expected. PubMed db
with `"pubmed pmc open access"[sb]` returns ~2400 with the same query. This
is because PMC db indexing differs from PubMed.

Strategy: search PubMed (broader) with OA subset filter → get PMIDs →
elink PMID→PMC ID (handled in `linking.py`) → fetch full XML from PMC db.

Rate limit:
- Without API key: 3 req/sec
- With API key:    10 req/sec
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator, Optional

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
RATE_LIMIT_DELAY = 0.34   # 3 req/sec


def build_pubmed_query(
    cutoff_date: str = "2024/01/01",
    end_date: Optional[str] = None,
    extra_mesh: Optional[list[str]] = None,
) -> str:
    """Build PubMed query string for rare-disease case reports in PMC OA.

    MeSH heads kept conservative: 'Rare Diseases' + 'Genetic Diseases, Inborn'.
    Extra MeSH terms can be added via `extra_mesh`.
    """
    mesh_terms = ['"Rare Diseases"[MeSH]', '"Genetic Diseases, Inborn"[MeSH]']
    if extra_mesh:
        mesh_terms.extend(f'"{m}"[MeSH]' for m in extra_mesh)
    mesh_clause = "(" + " OR ".join(mesh_terms) + ")"

    end = end_date or "3000"
    return " AND ".join([
        mesh_clause,
        '"case reports"[Publication Type]',
        f'("{cutoff_date}"[PDAT] : "{end}"[PDAT])',
        '"pubmed pmc open access"[sb]',
    ])


def search_pubmed_pmids(
    cutoff_date: str = "2024/01/01",
    end_date: Optional[str] = None,
    retmax_per_page: int = 200,
    max_total: Optional[int] = None,
    api_key: Optional[str] = None,
) -> Iterator[str]:
    """Yield PMIDs matching the rare-disease + case-report + OA filter."""
    query = build_pubmed_query(cutoff_date, end_date)
    retstart = 0
    total_yielded = 0

    while True:
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retstart": retstart,
            "retmax": retmax_per_page,
            "sort": "pub_date",   # newest first; helps with checkpointing
        }
        if api_key:
            params["api_key"] = api_key

        r = requests.get(ESEARCH_URL, params=params, timeout=30)
        r.raise_for_status()
        result = r.json().get("esearchresult", {})

        ids = result.get("idlist", [])
        if not ids:
            return

        for pmid in ids:
            yield pmid
            total_yielded += 1
            if max_total and total_yielded >= max_total:
                return

        retstart += len(ids)
        total_count = int(result.get("count", 0))
        if retstart >= total_count:
            return

        time.sleep(RATE_LIMIT_DELAY)


def get_total_count(
    cutoff_date: str = "2024/01/01",
    end_date: Optional[str] = None,
    api_key: Optional[str] = None,
) -> int:
    """Just return the total count without paginating."""
    query = build_pubmed_query(cutoff_date, end_date)
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": 0,
    }
    if api_key:
        params["api_key"] = api_key
    r = requests.get(ESEARCH_URL, params=params, timeout=30)
    r.raise_for_status()
    return int(r.json().get("esearchresult", {}).get("count", 0))


def save_pmids_to_file(
    out_path: Path | str,
    cutoff_date: str = "2024/01/01",
    end_date: Optional[str] = None,
    max_total: Optional[int] = None,
) -> int:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w") as f:
        for pmid in search_pubmed_pmids(cutoff_date, end_date, max_total=max_total):
            f.write(json.dumps({"pmid": pmid}) + "\n")
            count += 1
            if count % 200 == 0:
                print(f"  [search] {count} PMIDs collected...", flush=True)
    return count


# backward-compatible aliases
def search_candidates(*args, **kwargs):  # pragma: no cover
    return search_pubmed_pmids(*args, **kwargs)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", default="2024/01/01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--max", type=int, default=None)
    parser.add_argument(
        "--out",
        default="/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/01_pmids.jsonl",
    )
    args = parser.parse_args()

    total = get_total_count(args.cutoff, args.end)
    print(f"Total matching: {total}")
    n = save_pmids_to_file(args.out, args.cutoff, args.end, args.max)
    print(f"DONE: wrote {n} PMIDs to {args.out}")

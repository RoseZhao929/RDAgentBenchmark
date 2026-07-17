"""Step 1.5: Batch convert PMIDs to PMC IDs via E-utils elink.

PubMed search gives PMIDs; we need PMC IDs to fetch full XML from db=pmc.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

import requests

ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
RATE_LIMIT_DELAY = 0.34
BATCH_SIZE = 200


def pmid_to_pmc_batch(pmids: list[str], api_key: Optional[str] = None) -> dict[str, str]:
    """Map a batch of PMIDs to PMC IDs (those with PMC entries).

    Returns {pmid: pmc_id} for PMIDs that have PMC entries; PMIDs without
    PMC are omitted.
    """
    if not pmids:
        return {}

    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": ",".join(pmids),
        "linkname": "pubmed_pmc",
    }
    if api_key:
        params["api_key"] = api_key

    r = requests.get(ELINK_URL, params=params, timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    result: dict[str, str] = {}
    for linkset in root.findall(".//LinkSet"):
        # Source PMIDs in IdList
        src_pmids = [e.text for e in linkset.findall("./IdList/Id") if e.text]
        # Linked PMC IDs in LinkSetDb (linkname=pubmed_pmc)
        pmc_ids = [
            e.text
            for e in linkset.findall("./LinkSetDb/Link/Id")
            if e.text
        ]
        # When 1-to-1 (which is typical for pubmed_pmc), zip by order
        for pmid, pmc in zip(src_pmids, pmc_ids):
            result[pmid] = pmc
    return result


def batch_link_to_file(
    pmids: Iterable[str],
    out_path: Path | str,
    api_key: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Convert a stream of PMIDs to PMC IDs and write {pmid, pmc_id} JSONL.

    Returns stats: {"linked": N, "unlinked": N}.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pmids_list = list(pmids)
    n = len(pmids_list)
    stats = {"linked": 0, "unlinked": 0}

    with out_path.open("w") as f:
        for i in range(0, n, batch_size):
            batch = pmids_list[i : i + batch_size]
            mapping = pmid_to_pmc_batch(batch, api_key=api_key)
            for pmid in batch:
                pmc_id = mapping.get(pmid)
                if pmc_id:
                    f.write(json.dumps({"pmid": pmid, "pmc_id": pmc_id}) + "\n")
                    stats["linked"] += 1
                else:
                    stats["unlinked"] += 1
            print(f"  [elink] processed {min(i + batch_size, n)}/{n} "
                  f"linked={stats['linked']} unlinked={stats['unlinked']}", flush=True)
            time.sleep(RATE_LIMIT_DELAY)

    return stats


def read_pmids(path: Path | str) -> list[str]:
    out = []
    with Path(path).open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line)["pmid"])
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pmids",
        default="/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/01_pmids.jsonl",
    )
    parser.add_argument(
        "--out",
        default="/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/02_pmid_to_pmc.jsonl",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    pmids = read_pmids(args.pmids)
    if args.limit:
        pmids = pmids[: args.limit]
    print(f"Linking {len(pmids)} PMIDs to PMC IDs...")
    stats = batch_link_to_file(pmids, args.out)
    print(f"DONE: {stats}")

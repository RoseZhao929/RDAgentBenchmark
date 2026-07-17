"""Step 2: E-utils efetch full JATS XML for each candidate PMC ID.

Rate limit: 3 req/sec (no key) / 10 req/sec (with key).
"""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path
from typing import Iterable, Optional

import requests

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
RATE_LIMIT_DELAY = 0.34


def fetch_xml(pmc_id: str, api_key: Optional[str] = None) -> bytes:
    """Fetch a single PMC article's JATS XML (gzipped on the wire? no, plain).

    Returns raw XML bytes. Raises on HTTP error.
    """
    params = {
        "db": "pmc",
        "id": pmc_id,
        "retmode": "xml",
    }
    if api_key:
        params["api_key"] = api_key
    r = requests.get(EFETCH_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.content


def batch_fetch_to_dir(
    pmc_ids: Iterable[str],
    out_dir: Path | str,
    gzip_output: bool = True,
    skip_existing: bool = True,
    api_key: Optional[str] = None,
) -> dict[str, int]:
    """Fetch many PMC XMLs in sequence, save one file per ID.

    Returns stats: {"ok": N, "fail": N, "skipped": N}.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    stats = {"ok": 0, "fail": 0, "skipped": 0}
    fail_log = out.parent / "fetch_failures.jsonl"

    for pmc_id in pmc_ids:
        ext = ".xml.gz" if gzip_output else ".xml"
        fp = out / f"PMC{pmc_id}{ext}"
        if skip_existing and fp.exists():
            stats["skipped"] += 1
            continue

        try:
            xml_bytes = fetch_xml(pmc_id, api_key=api_key)
            if gzip_output:
                with gzip.open(fp, "wb") as f:
                    f.write(xml_bytes)
            else:
                fp.write_bytes(xml_bytes)
            stats["ok"] += 1
        except Exception as e:
            stats["fail"] += 1
            with fail_log.open("a") as fl:
                fl.write(json.dumps({"pmc_id": pmc_id, "error": str(e)}) + "\n")

        if (stats["ok"] + stats["fail"]) % 100 == 0:
            print(f"  [fetch] ok={stats['ok']} fail={stats['fail']} skipped={stats['skipped']}",
                  flush=True)

        time.sleep(RATE_LIMIT_DELAY)

    return stats


def read_candidate_ids(jsonl_path: Path | str, field: str = "pmc_id") -> list[str]:
    """Load PMC IDs from a JSONL file (one ID per line on the given field)."""
    ids = []
    with Path(jsonl_path).open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            v = rec.get(field)
            if v:
                ids.append(v)
    return ids


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PMC OA batch XML fetch")
    parser.add_argument(
        "--candidates",
        default="/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/02_pmid_to_pmc.jsonl",
    )
    parser.add_argument("--field", default="pmc_id")
    parser.add_argument(
        "--out-dir",
        default="/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/03_xml",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    ids = read_candidate_ids(args.candidates, field=args.field)
    if args.limit:
        ids = ids[: args.limit]
    print(f"Fetching {len(ids)} PMC articles...")
    stats = batch_fetch_to_dir(ids, args.out_dir)
    print(f"DONE: {stats}")

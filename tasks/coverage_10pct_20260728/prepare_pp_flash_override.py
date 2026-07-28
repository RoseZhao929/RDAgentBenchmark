#!/usr/bin/env python3
"""Seed the post-regex-fix PP/MAI-DxO Flash prefix rerun.

The first 78 rows in the Phase 4a file are the frozen pre-fix receipts.  Later
rows are new attempts made with the corrected parser.  This script copies only
post-fix attempts for the first 78 target cases into a separate resume file;
the runner can then execute the old successful cases that otherwise would have
been skipped.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase4a_runner import load_phenopacket_store  # noqa: E402

SOURCE = (
    ROOT
    / "data/round2/phase4a"
    / "predictions_phenopacket_store_maidxo_deepseek_deepseek-v4-flash.jsonl"
)
DESTINATION = (
    ROOT
    / "logs/coverage_10pct_20260728/fixed_prefix"
    / "pp_flash_head78.jsonl"
)
FROZEN_PREFIX_ROWS = 78


def main() -> int:
    rows = [
        json.loads(line)
        for line in SOURCE.read_text().splitlines()
        if line.strip()
    ]
    expected = {
        str(case.case_id)
        for case in load_phenopacket_store(n=FROZEN_PREFIX_ROWS)
    }
    frozen = rows[:FROZEN_PREFIX_ROWS]
    frozen_ids = [str(row.get("case_id")) for row in frozen]
    if len(frozen_ids) != FROZEN_PREFIX_ROWS:
        raise RuntimeError("source does not contain the 78-row frozen prefix")
    if len(set(frozen_ids)) != FROZEN_PREFIX_ROWS:
        raise RuntimeError("frozen prefix contains duplicate case IDs")
    if set(frozen_ids) != expected:
        raise RuntimeError("frozen prefix does not match the expected n=78 cases")

    post_fix = [
        row
        for row in rows[FROZEN_PREFIX_ROWS:]
        if str(row.get("case_id")) in expected
    ]
    post_fix_ids = {str(row["case_id"]) for row in post_fix}
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{DESTINATION.name}.",
        suffix=".tmp",
        dir=DESTINATION.parent,
    )
    try:
        with os.fdopen(fd, "w") as handle:
            for row in post_fix:
                handle.write(
                    json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, DESTINATION)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise

    print(
        json.dumps(
            {
                "source_rows": len(rows),
                "post_fix_attempt_rows": len(post_fix),
                "post_fix_case_ids": len(post_fix_ids),
                "remaining_prefix_case_ids": FROZEN_PREFIX_ROWS
                - len(post_fix_ids),
                "destination": str(DESTINATION.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

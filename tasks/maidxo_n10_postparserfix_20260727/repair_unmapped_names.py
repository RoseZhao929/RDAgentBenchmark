#!/usr/bin/env python3
"""Repair pre-fix MAI-DxO rows that discarded explicit NL diagnoses."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


TARGET_ERROR = (
    "MAI-DxO produced no explicit ontology ID or conservatively validated "
    "Orphanet disease-name mapping."
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.receipt.open()]
    repaired = 0
    for row in rows:
        if (
            row.get("status") != "parser_error"
            or row.get("error_message") != TARGET_ERROR
        ):
            continue
        extra = row.get("extra") or {}
        candidates = [
            extra.get("maidxo_raw_final_diagnosis"),
            *(extra.get("maidxo_raw_differential") or {}).keys(),
        ]
        predictions = []
        for candidate in candidates:
            name = str(candidate or "").strip()
            if (
                not name
                or name.lower().startswith(
                    (
                        "unable to establish",
                        "diagnosis not reached",
                        "no diagnosis",
                    )
                )
                or name in predictions
            ):
                continue
            predictions.append(name)
        if not predictions:
            continue
        row["ranked_predictions"] = predictions[:5]
        row["confidence_scores"] = [
            float((extra.get("maidxo_raw_differential") or {}).get(name, 1.0))
            for name in predictions[:5]
        ]
        row["status"] = "ok"
        row["error_message"] = None
        extra["maidxo_receipt_repair"] = {
            "reason": "explicit_nl_diagnosis_was_discarded_by_strict_orpha_map",
            "source": "stored_raw_final_and_differential",
        }
        row["extra"] = extra
        repaired += 1

    fd, tmp_name = tempfile.mkstemp(
        prefix=args.receipt.name + ".", dir=args.receipt.parent
    )
    try:
        with os.fdopen(fd, "w") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, args.receipt)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    print(json.dumps({"receipt": str(args.receipt), "repaired": repaired}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

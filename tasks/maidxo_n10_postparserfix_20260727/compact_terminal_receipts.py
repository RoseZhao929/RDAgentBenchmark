#!/usr/bin/env python3
"""Compact resumed receipts without cherry-picking model abstentions."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path


def is_model_abstention(row: dict) -> bool:
    if row.get("status") != "parser_error" or row.get("ranked_predictions"):
        return False
    extra = row.get("extra") or {}
    if extra.get("maidxo_fatal_runtime_hits"):
        return False
    raw = str(extra.get("maidxo_raw_final_diagnosis") or "").strip().casefold()
    return raw.startswith(
        (
            "unable to establish",
            "unable to determine",
            "unable to identify",
            "cannot establish",
            "no diagnosis",
        )
    )


def is_supervisor_interruption(row: dict) -> bool:
    return (
        row.get("status") == "agent_error"
        and "returncode=-9" in str(row.get("error_message") or "")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    chosen: OrderedDict[str, tuple[dict, str]] = OrderedDict()
    stats = {
        "input_rows": 0,
        "dropped_supervisor_interruptions": 0,
        "dropped_duplicate_attempts": 0,
        "recovered_non_ok_with_ok": 0,
        "preserved_first_abstentions": 0,
    }
    for raw_line in args.source.open(errors="replace"):
        if not raw_line.strip():
            continue
        stats["input_rows"] += 1
        row = json.loads(raw_line)
        case_id = str(row.get("case_id"))
        if is_supervisor_interruption(row):
            stats["dropped_supervisor_interruptions"] += 1
            continue
        previous = chosen.get(case_id)
        if previous is None:
            chosen[case_id] = (row, raw_line.rstrip("\n"))
            continue
        previous_row, _ = previous
        stats["dropped_duplicate_attempts"] += 1
        # A complete first-run abstention is the method's real outcome. Never
        # replace it with a stochastic retry that happened after a restart.
        if is_model_abstention(previous_row):
            stats["preserved_first_abstentions"] += 1
            continue
        # Infrastructure failures may be retried; keep the first later valid
        # result, but never replace one valid result with another sample.
        if previous_row.get("status") != "ok" and row.get("status") == "ok":
            chosen[case_id] = (row, raw_line.rstrip("\n"))
            stats["recovered_non_ok_with_ok"] += 1

    args.destination.write_text(
        "\n".join(raw_line for _, raw_line in chosen.values()) + "\n"
    )
    stats["output_rows"] = len(chosen)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

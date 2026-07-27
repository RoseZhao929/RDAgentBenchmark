#!/usr/bin/env python3
"""Semantic gate for MAI-DxO smoke receipts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.agents.maidxo import _is_noise_candidate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--expected-unique", type=int, required=True)
    parser.add_argument("--min-ok", type=int, required=True)
    args = parser.parse_args()

    rows = []
    malformed = 0
    if args.receipt.exists():
        for line in args.receipt.open(errors="replace"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1

    latest = {
        str(row["case_id"]): row
        for row in rows
        if row.get("case_id") is not None
    }
    statuses = Counter(str(row.get("status")) for row in latest.values())
    valid_ok = 0
    semantic_errors = []
    for row in latest.values():
        if row.get("status") != "ok":
            continue
        predictions = [
            str(x).strip()
            for x in row.get("ranked_predictions") or []
            if str(x).strip()
        ]
        normalized = [value.casefold() for value in predictions]
        noise = [value for value in predictions if _is_noise_candidate(value)]
        if not predictions:
            semantic_errors.append(f"{row.get('case_id')}: empty predictions")
        elif noise:
            semantic_errors.append(
                f"{row.get('case_id')}: noise predictions={noise}"
            )
        elif len(normalized) != len(set(normalized)):
            semantic_errors.append(
                f"{row.get('case_id')}: duplicate predictions"
            )
        else:
            valid_ok += 1

    errors = []
    if malformed:
        errors.append(f"malformed={malformed}")
    if len(latest) != args.expected_unique:
        errors.append(
            f"unique={len(latest)}, expected={args.expected_unique}"
        )
    if statuses.get("agent_error", 0):
        errors.append(f"agent_error={statuses['agent_error']}")
    if statuses.get("timeout", 0):
        errors.append(f"timeout={statuses['timeout']}")
    if valid_ok < args.min_ok:
        errors.append(f"valid_ok={valid_ok}, required>={args.min_ok}")
    if semantic_errors:
        errors.extend(semantic_errors)

    payload = {
        "receipt": str(args.receipt),
        "unique": len(latest),
        "statuses": dict(statuses),
        "valid_ok": valid_ok,
        "passed": not errors,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

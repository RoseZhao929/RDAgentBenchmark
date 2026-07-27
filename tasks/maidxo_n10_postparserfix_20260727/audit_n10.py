#!/usr/bin/env python3
"""Audit the complete five-cell MAI-DxO run (N=10 by default)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.agents.maidxo import _is_noise_candidate  # noqa: E402
from scripts.phase4a_runner import (  # noqa: E402
    load_phenopacket_store,
    load_rarearena_rds,
    load_rarebench_stratified,
)


CELLS = {
    "pp_gpt5": (
        load_phenopacket_store,
        "predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl",
    ),
    "rarearena_v4flash": (
        load_rarearena_rds,
        "predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl",
    ),
    "rarearena_gpt5": (
        load_rarearena_rds,
        "predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl",
    ),
    "rarebench_v4flash": (
        load_rarebench_stratified,
        "predictions_rarebench_maidxo_deepseek_deepseek-v4-flash.jsonl",
    ),
    "rarebench_gpt5": (
        load_rarebench_stratified,
        "predictions_rarebench_maidxo_openai_gpt-5.jsonl",
    ),
}

FATAL_MARKERS = (
    "key limit exceeded",
    "no_available_channel",
    "incorrect api key",
    "authenticationerror",
)


def read_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    if not path.exists():
        return rows, ["missing receipt"]
    for line_number, line in enumerate(path.open(errors="replace"), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: malformed JSON ({exc})")
            continue
        if not isinstance(row, dict):
            errors.append(f"line {line_number}: JSON value is not an object")
            continue
        rows.append(row)
    return rows, errors


def expected_ids(loader, expected_n: int) -> list[str]:
    return [str(case.case_id) for case in loader(n=expected_n)]


def audit_cell(path: Path, loader, expected_n: int) -> dict:
    rows, errors = read_jsonl(path)
    expected = expected_ids(loader, expected_n)
    ids = [str(row.get("case_id")) for row in rows]
    counts = Counter(ids)
    duplicate_ids = sorted(case_id for case_id, n in counts.items() if n > 1)
    if len(rows) != expected_n:
        errors.append(f"rows={len(rows)}, expected={expected_n}")
    if duplicate_ids:
        errors.append(f"duplicate case_ids={duplicate_ids}")
    missing = sorted(set(expected) - set(ids))
    unexpected = sorted(set(ids) - set(expected))
    if missing:
        errors.append(f"missing expected case_ids={missing}")
    if unexpected:
        errors.append(f"unexpected case_ids={unexpected}")

    statuses = Counter(str(row.get("status")) for row in rows)
    if statuses != Counter({"ok": expected_n}):
        errors.append(
            f"statuses={dict(statuses)}, expected={{'ok': {expected_n}}}"
        )

    row_issues: dict[str, list[str]] = {}
    for row in rows:
        case_id = str(row.get("case_id"))
        issues: list[str] = []
        predictions = [
            str(value).strip()
            for value in (row.get("ranked_predictions") or [])
            if str(value).strip()
        ]
        if not predictions:
            issues.append("empty ranked_predictions")
        noise = [value for value in predictions if _is_noise_candidate(value)]
        if noise:
            issues.append(f"noise predictions={noise}")
        normalized = [value.casefold() for value in predictions]
        if len(normalized) != len(set(normalized)):
            issues.append("duplicate ranked_predictions")
        confidences = row.get("confidence_scores") or []
        if confidences and len(confidences) != len(predictions):
            issues.append(
                f"confidence count {len(confidences)} != prediction count "
                f"{len(predictions)}"
            )
        if not isinstance(row.get("total_latency_ms"), (int, float)) or (
            row.get("total_latency_ms") or 0
        ) <= 0:
            issues.append("missing/non-positive total_latency_ms")
        extra = row.get("extra") or {}
        if extra.get("maidxo_fatal_runtime_hits"):
            issues.append(
                f"fatal runtime hits={extra['maidxo_fatal_runtime_hits']}"
            )
        if not extra.get("maidxo_raw_final_diagnosis"):
            issues.append("missing raw final diagnosis")
        if not extra.get("maidxo_raw_differential"):
            issues.append("missing raw differential")
        searchable = json.dumps(
            {
                "error_message": row.get("error_message"),
                "fatal_hits": extra.get("maidxo_fatal_runtime_hits"),
            },
            ensure_ascii=False,
        ).casefold()
        hits = [marker for marker in FATAL_MARKERS if marker in searchable]
        if hits:
            issues.append(f"fatal markers={hits}")
        if issues:
            row_issues[case_id] = issues
    if row_issues:
        errors.append(f"{len(row_issues)} rows failed semantic/runtime checks")

    total_latency_ms = sum(
        float(row.get("total_latency_ms") or 0) for row in rows
    )
    receipt_cost_estimate = sum(
        float((row.get("cost") or {}).get("cost_usd") or 0) for row in rows
    )
    return {
        "receipt": str(path),
        "rows": len(rows),
        "statuses": dict(statuses),
        "expected_case_ids": expected,
        "n2_prefix_case_ids": expected[:2],
        "row_issues": row_issues,
        "total_latency_seconds": round(total_latency_ms / 1000, 3),
        "receipt_side_cost_estimate_usd": round(receipt_cost_estimate, 6),
        "passed": not errors,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--receipts-dir",
        type=Path,
        default=ROOT
        / "logs"
        / "maidxo_n10_postparserfix_20260727"
        / "receipts",
    )
    parser.add_argument(
        "--phase4a-dir",
        type=Path,
        help=(
            "Audit the committed standard Phase 4a filenames instead of "
            "the local cell-ID receipt filenames."
        ),
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--expected-n", type=int, default=10)
    args = parser.parse_args()

    cells = {}
    for cell_id, (loader, phase4a_filename) in CELLS.items():
        path = (
            args.phase4a_dir / phase4a_filename
            if args.phase4a_dir
            else args.receipts_dir / f"{cell_id}.jsonl"
        )
        cells[cell_id] = audit_cell(path, loader, args.expected_n)
    report = {
        "scope": (
            f"5 MAI-DxO cells x deterministic N={args.expected_n}"
        ),
        "cells": cells,
        "total_rows": sum(cell["rows"] for cell in cells.values()),
        "passed": all(cell["passed"] for cell in cells.values()),
        "cost_note": (
            "Receipt cost_usd is a harness-side token estimate, not an "
            "AIHubMix billing receipt."
        ),
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Print an auditable progress snapshot for the five MAI-DxO N=100 cells."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
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


def is_model_abstention(row: dict) -> bool:
    """Return true for a completed MAI-DxO run that explicitly abstained."""
    if row.get("status") != "parser_error":
        return False
    if row.get("ranked_predictions"):
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


def inspect(path: Path, expected_ids: set[str]) -> dict:
    rows: list[dict] = []
    malformed = 0
    if path.exists():
        for line in path.open(errors="replace"):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    latest = {
        str(row.get("case_id")): row
        for row in rows
        if row.get("case_id") is not None
    }
    attempt_counts = Counter(
        str(row.get("case_id"))
        for row in rows
        if row.get("case_id") is not None
    )
    duplicate_attempts = {
        case_id: count
        for case_id, count in attempt_counts.items()
        if count > 1
    }
    issues: dict[str, list[str]] = {}
    terminal_abstentions: dict[str, str] = {}
    for case_id, row in latest.items():
        row_issues: list[str] = []
        status = str(row.get("status"))
        abstention = is_model_abstention(row)
        predictions = [
            str(value).strip()
            for value in row.get("ranked_predictions") or []
            if str(value).strip()
        ]
        if abstention:
            terminal_abstentions[case_id] = str(
                (row.get("extra") or {}).get(
                    "maidxo_raw_final_diagnosis"
                )
            )
        elif status != "ok":
            row_issues.append(f"status={status}")
        if status == "ok" and not predictions:
            row_issues.append("empty predictions")
        noise = [value for value in predictions if _is_noise_candidate(value)]
        if noise:
            row_issues.append(f"noise={noise}")
        normalized = [value.casefold() for value in predictions]
        if len(normalized) != len(set(normalized)):
            row_issues.append("duplicate predictions")
        confidences = row.get("confidence_scores") or []
        if confidences and len(confidences) != len(predictions):
            row_issues.append(
                f"confidence count={len(confidences)}, "
                f"prediction count={len(predictions)}"
            )
        if not isinstance(row.get("total_latency_ms"), (int, float)) or (
            row.get("total_latency_ms") or 0
        ) <= 0:
            row_issues.append("missing/non-positive latency")
        extra = row.get("extra") or {}
        if status == "ok" and not extra.get("maidxo_raw_final_diagnosis"):
            row_issues.append("missing raw final diagnosis")
        if status == "ok" and not extra.get("maidxo_raw_differential"):
            row_issues.append("missing raw differential")
        if extra.get("maidxo_fatal_runtime_hits"):
            row_issues.append(
                f"fatal={extra['maidxo_fatal_runtime_hits']}"
            )
        searchable = json.dumps(
            {
                "error": row.get("error_message"),
                "fatal": extra.get("maidxo_fatal_runtime_hits"),
            }
        ).casefold()
        hits = [marker for marker in FATAL_MARKERS if marker in searchable]
        if hits:
            row_issues.append(f"fatal markers={hits}")
        if row_issues:
            issues[case_id] = row_issues
    statuses = Counter(str(row.get("status")) for row in latest.values())
    unexpected = sorted(set(latest) - expected_ids)
    return {
        "raw_rows": len(rows),
        "unique": len(latest),
        "expected_completed": len(set(latest) & expected_ids),
        "remaining": len(expected_ids - set(latest)),
        "statuses": dict(statuses),
        "malformed": malformed,
        "duplicate_attempts": duplicate_attempts,
        "unexpected_case_ids": unexpected,
        "terminal_abstentions": terminal_abstentions,
        "issues": issues,
        "mtime": (
            datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            if path.exists()
            else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase4a-dir",
        type=Path,
        default=ROOT / "data" / "round2" / "phase4a",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    cells = {}
    for cell_id, (loader, filename) in CELLS.items():
        expected = {str(case.case_id) for case in loader(n=100)}
        cells[cell_id] = inspect(args.phase4a_dir / filename, expected)
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "cells": cells,
        "total_expected_completed": sum(
            cell["expected_completed"] for cell in cells.values()
        ),
        "total_remaining": sum(cell["remaining"] for cell in cells.values()),
        "has_issues": any(
            cell["malformed"]
            or cell["duplicate_attempts"]
            or cell["unexpected_case_ids"]
            or cell["issues"]
            for cell in cells.values()
        ),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n")
    if payload["has_issues"]:
        return 2
    return 0 if payload["total_remaining"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

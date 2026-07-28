#!/usr/bin/env python3
"""End-to-end audit for the nine 10%-coverage Phase 4a cells."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase4a_runner import (  # noqa: E402
    load_phenopacket_store,
    load_rarearena_rds,
    load_rarebench_stratified,
)
from tasks.coverage_10pct_20260728.run_yutian import (  # noqa: E402
    CELLS,
    OUT_DIR,
    STATE_DIR,
)

LOADERS = {
    "phenopacket_store": load_phenopacket_store,
    "rarearena_rds": load_rarearena_rds,
    "rarebench": load_rarebench_stratified,
}


def audit_cell(cell) -> dict:
    path = OUT_DIR / cell.filename
    rows = []
    malformed = 0
    for line in path.open(errors="replace"):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            malformed += 1
    expected_cases = LOADERS[cell.dataset](n=cell.target)
    expected = {str(case.case_id) for case in expected_cases}
    by_id = {str(row.get("case_id")): row for row in rows}
    issues: dict[str, list[str]] = {}
    for case_id, row in by_id.items():
        row_issues = []
        if row.get("agent_id") != cell.agent:
            row_issues.append(f"agent_id={row.get('agent_id')!r}")
        if row.get("backbone_id") != cell.backbone:
            row_issues.append(f"backbone_id={row.get('backbone_id')!r}")
        if not isinstance(row.get("total_latency_ms"), (int, float)) or (
            row.get("total_latency_ms") or 0
        ) <= 0:
            row_issues.append("missing/non-positive latency")
        predictions = list(row.get("ranked_predictions") or [])
        confidences = list(row.get("confidence_scores") or [])
        normalized = [
            " ".join(str(value).split()).casefold()
            for value in predictions
        ]
        if len(normalized) != len(set(normalized)):
            row_issues.append("duplicate predictions")
        if confidences and len(confidences) != len(predictions):
            row_issues.append("confidence/prediction length mismatch")
        if row.get("status") == "ok" and not predictions:
            row_issues.append("ok with empty predictions")
        if row.get("status") not in {
            "ok",
            "skipped",
            "parser_error",
            "agent_error",
            "timeout",
        }:
            row_issues.append(f"unknown status={row.get('status')!r}")
        if row_issues:
            issues[case_id] = row_issues
    missing = sorted(expected - set(by_id))
    unexpected = sorted(set(by_id) - expected)
    statuses = Counter(str(row.get("status")) for row in rows)
    scoreable = statuses["ok"] + statuses["parser_error"] + statuses["skipped"]
    infrastructure_failures = statuses["agent_error"] + statuses["timeout"]
    coverage_passed = (
        malformed == 0
        and len(rows) == cell.target
        and len(by_id) == cell.target
        and not missing
        and not unexpected
        and not issues
        and infrastructure_failures == 0
    )
    return {
        "file": str(path.relative_to(ROOT)),
        "rows": len(rows),
        "unique": len(by_id),
        "target": cell.target,
        "statuses": dict(statuses),
        "ok_rate": round(statuses["ok"] / cell.target, 4),
        "scoreable": scoreable,
        "scoreable_rate": round(scoreable / cell.target, 4),
        "infrastructure_failures": infrastructure_failures,
        "missing_case_ids": missing,
        "unexpected_case_ids": unexpected,
        "malformed": malformed,
        "row_issues": issues,
        "coverage_passed": coverage_passed,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    cells = {cell.cell_id: audit_cell(cell) for cell in CELLS}
    payload = {
        "scope": "PLAN_yutian.md nine cells at 10% development coverage",
        "total_target": sum(cell.target for cell in CELLS),
        "total_rows": sum(value["rows"] for value in cells.values()),
        "total_ok": sum(
            value["statuses"].get("ok", 0) for value in cells.values()
        ),
        "total_parser_error": sum(
            value["statuses"].get("parser_error", 0)
            for value in cells.values()
        ),
        "total_agent_error": sum(
            value["statuses"].get("agent_error", 0)
            for value in cells.values()
        ),
        "total_timeout": sum(
            value["statuses"].get("timeout", 0)
            for value in cells.values()
        ),
        "coverage_passed": all(
            value["coverage_passed"] for value in cells.values()
        ),
        "cells": cells,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    report = STATE_DIR / "audit_yutian.json"
    report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["coverage_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

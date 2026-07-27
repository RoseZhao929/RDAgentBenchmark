#!/usr/bin/env python3
"""Strict completion gate for the five MAI-DxO N=100 cells."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from functools import lru_cache

TASK_DIR = Path(__file__).resolve().parent
ROOT = TASK_DIR.parents[1]
sys.path.insert(0, str(ROOT))

from harness.agents.maidxo import (  # noqa: E402
    _accept_orpha_mapping,
    _clean_for_fuzzy,
    _is_noise_candidate,
)
from harness.pmc_oa.orphanet import map_diagnosis, parse_orphadata  # noqa: E402
from monitor import CELLS, DETAIL_BLOCK, MAX_ATTEMPTS, TERMINAL  # noqa: E402
from scripts.phase4a_runner import (  # noqa: E402
    load_phenopacket_store,
    load_rarearena_rds,
    load_rarebench_stratified,
)

OUT_DIR = ROOT / "data" / "round2" / "phase4a"
STATE_DIR = ROOT / "logs" / "maidxo_missing_n100_20260727" / "state"
ORPHA_TABLES = parse_orphadata()


@lru_cache(maxsize=None)
def expected_case_ids(cell_id: str) -> frozenset[str]:
    """Reconstruct the exact deterministic N=100 sample used by the runner."""
    if cell_id == "pp_gpt5":
        cases = load_phenopacket_store(n=100, seed=42)
    elif cell_id.startswith("rarearena_"):
        cases = load_rarearena_rds(n=100, seed=42)
    elif cell_id.startswith("rarebench_"):
        cases = load_rarebench_stratified(n_per_split=25, seed=42)
    else:
        raise ValueError(f"no expected-case loader for {cell_id}")
    return frozenset(str(case.case_id) for case in cases)


def audit_cell(cell_id: str, filename: str) -> tuple[dict, list[str]]:
    path = OUT_DIR / filename
    errors: list[str] = []
    rows: list[dict] = []
    malformed = 0
    if path.exists():
        for line in path.open(errors="replace"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    else:
        errors.append("receipt file missing")

    attempts: Counter[str] = Counter()
    latest: dict[str, dict] = {}
    terminal_seen: set[str] = set()
    post_terminal = 0
    total_cost = 0.0
    simulated_clinical_cost = 0.0
    total_latency_ms = 0
    for row_index, row in enumerate(rows, 1):
        case_id = row.get("case_id")
        if case_id is None:
            errors.append(f"row {row_index}: missing case_id")
            continue
        case_id = str(case_id)
        if case_id in terminal_seen:
            post_terminal += 1
        attempts[case_id] += 1
        latest[case_id] = row
        status = row.get("status")
        if status in TERMINAL:
            terminal_seen.add(case_id)

        total_cost += float((row.get("cost") or {}).get("cost_usd") or 0.0)
        extra = row.get("extra") or {}
        if "simulated_cost_usd" in extra:
            errors.append(
                f"row {row_index}/{case_id}: deprecated ambiguous simulated cost key"
            )
        simulated_clinical_cost += float(
            extra.get("maidxo_simulated_clinical_cost_usd") or 0.0
        )
        total_latency_ms += int(row.get("total_latency_ms") or 0)

        blocks = {
            " ".join(block.split())
            for block in DETAIL_BLOCK.findall(row.get("reasoning_trace") or "")
        }
        if len(blocks) > 1:
            errors.append(f"row {row_index}/{case_id}: cross-case trace blocks")

        if status == "parser_error":
            extra = row.get("extra") or {}
            if float((row.get("cost") or {}).get("cost_usd") or 0.0) <= 0:
                errors.append(f"row {row_index}/{case_id}: parser_error has zero cost")
            if not row.get("reasoning_trace"):
                errors.append(f"row {row_index}/{case_id}: parser_error missing trace")
            if "maidxo_raw_final_diagnosis" not in extra:
                errors.append(
                    f"row {row_index}/{case_id}: parser_error missing raw diagnosis"
                )
        if status == "ok":
            predictions = [str(x) for x in row.get("ranked_predictions") or []]
            if not predictions:
                errors.append(f"row {row_index}/{case_id}: ok has no predictions")
            noisy = [x for x in predictions if _is_noise_candidate(x)]
            if noisy:
                errors.append(
                    f"row {row_index}/{case_id}: ok retains noisy predictions "
                    f"{noisy[:2]!r}"
                )
            for audit in extra.get("maidxo_fuzzy_fallback") or []:
                if not isinstance(audit, dict) or audit.get("type") != "fuzzy":
                    continue
                source = str(audit.get("input") or "")
                query = _clean_for_fuzzy(source) or source
                mapped = map_diagnosis(query, ORPHA_TABLES, return_top_k=5)
                if not mapped.get("orpha_id") and query != source:
                    query = source
                    mapped = map_diagnosis(query, ORPHA_TABLES, return_top_k=5)
                if not _accept_orpha_mapping(query, mapped):
                    invalid_id = str(
                        audit.get("orpha") or mapped.get("orpha_id") or ""
                    ).upper()
                    if invalid_id and invalid_id in {
                        prediction.upper() for prediction in predictions
                    }:
                        errors.append(
                            f"row {row_index}/{case_id}: ok retains unsafe fuzzy "
                            f"mapping {source!r} -> {invalid_id}"
                        )

    if malformed:
        errors.append(f"malformed JSONL rows={malformed}")
    if len(latest) != 100:
        errors.append(f"unique cases={len(latest)}, expected 100")
    expected = expected_case_ids(cell_id)
    observed = set(latest)
    missing_expected = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if missing_expected or unexpected:
        errors.append(
            "case-id sample mismatch: "
            f"missing_expected={missing_expected[:3]!r} "
            f"unexpected={unexpected[:3]!r}"
        )
    if post_terminal:
        errors.append(f"receipts after a terminal result={post_terminal}")

    statuses = Counter()
    unsettled = []
    for case_id, row in latest.items():
        status = str(row.get("status"))
        statuses[status] += 1
        if status not in TERMINAL and attempts[case_id] < MAX_ATTEMPTS:
            unsettled.append(case_id)
    if unsettled:
        errors.append(f"retryable/unsettled cases={len(unsettled)}")
    if any(count > MAX_ATTEMPTS for count in attempts.values()):
        errors.append("one or more cases exceed retry ceiling")
    if not (STATE_DIR / f"{cell_id}.done").exists():
        errors.append("done marker missing")

    return {
        "cell_id": cell_id,
        "file": str(path.relative_to(ROOT)),
        "receipts": len(rows),
        "unique_cases": len(latest),
        "expected_case_set_match": not missing_expected and not unexpected,
        "statuses": dict(statuses),
        "cost_usd": total_cost,
        "simulated_clinical_cost_usd": simulated_clinical_cost,
        "receipt_latency_hours": total_latency_ms / 3_600_000,
        "max_attempts_observed": max(attempts.values(), default=0),
        "post_terminal_receipts": post_terminal,
    }, errors


def main() -> int:
    cells = []
    failures: dict[str, list[str]] = {}
    for cell_id, filename in CELLS:
        report, errors = audit_cell(cell_id, filename)
        cells.append(report)
        if errors:
            failures[cell_id] = errors

    payload = {
        "passed": not failures,
        "target_case_cells": 500,
        "audited_unique_case_cells": sum(x["unique_cases"] for x in cells),
        "total_receipts": sum(x["receipts"] for x in cells),
        "total_cost_usd": sum(x["cost_usd"] for x in cells),
        "total_simulated_clinical_cost_usd": sum(
            x["simulated_clinical_cost_usd"] for x in cells
        ),
        "cells": cells,
        "failures": failures,
    }
    output = TASK_DIR / "final_audit.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

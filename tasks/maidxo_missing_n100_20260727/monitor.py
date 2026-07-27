#!/usr/bin/env python3
"""One-shot health/progress check used by the MAI-DxO supervisor."""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import sys

TASK_DIR = Path(__file__).resolve().parent
ROOT = TASK_DIR.parents[1]
sys.path.insert(0, str(ROOT))

from harness.agents.maidxo import _is_noise_candidate  # noqa: E402

OUT_DIR = ROOT / "data" / "round2" / "phase4a"
LOG_DIR = ROOT / "logs" / "maidxo_missing_n100_20260727"
TERMINAL = {"ok", "skipped", "parser_error"}
MAX_ATTEMPTS = 3

CELLS = [
    ("pp_gpt5", "predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl"),
    ("rarearena_v4flash", "predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl"),
    ("rarearena_gpt5", "predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl"),
    ("rarebench_v4flash", "predictions_rarebench_maidxo_deepseek_deepseek-v4-flash.jsonl"),
    ("rarebench_gpt5", "predictions_rarebench_maidxo_openai_gpt-5.jsonl"),
]

DETAIL_BLOCK = re.compile(
    r"Full Case Details \(for your reference only\):\s*---\s*(.*?)\s*---",
    re.DOTALL,
)


def inspect(path: Path) -> dict:
    rows: list[dict] = []
    malformed = 0
    if path.exists():
        for line in path.open(errors="replace"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1

    attempts: Counter[str] = Counter()
    latest: dict[str, dict] = {}
    cross_case = 0
    suspicious_ok = 0
    incomplete_parser_audit = 0
    terminal_seen: set[str] = set()
    post_terminal_receipts = 0
    fatal_runtime = 0
    for row in rows:
        case_id = row.get("case_id")
        if case_id is None:
            continue
        case_id = str(case_id)
        if case_id in terminal_seen:
            post_terminal_receipts += 1
        attempts[case_id] += 1
        latest[case_id] = row
        if row.get("status") == "ok":
            predictions = [str(x) for x in row.get("ranked_predictions") or []]
            if not predictions or any(_is_noise_candidate(x) for x in predictions):
                suspicious_ok += 1
        if row.get("status") == "parser_error":
            cost = float((row.get("cost") or {}).get("cost_usd") or 0.0)
            extra = row.get("extra") or {}
            if (
                cost <= 0
                or not row.get("reasoning_trace")
                or "maidxo_raw_final_diagnosis" not in extra
            ):
                incomplete_parser_audit += 1
        if (row.get("extra") or {}).get("maidxo_fatal_runtime_hits"):
            fatal_runtime += 1
        blocks = {
            re.sub(r"\s+", " ", block).strip()
            for block in DETAIL_BLOCK.findall(row.get("reasoning_trace") or "")
        }
        if len(blocks) > 1:
            cross_case += 1
        if row.get("status") in TERMINAL:
            terminal_seen.add(case_id)

    statuses = Counter(str(row.get("status")) for row in latest.values())
    settled = {
        case_id
        for case_id, row in latest.items()
        if row.get("status") in TERMINAL or attempts[case_id] >= MAX_ATTEMPTS
    }
    retryable = {
        case_id
        for case_id, row in latest.items()
        if row.get("status") not in TERMINAL and attempts[case_id] < MAX_ATTEMPTS
    }
    age = time.time() - path.stat().st_mtime if path.exists() else None
    return {
        "receipts": len(rows),
        "unique": len(latest),
        "settled": len(settled),
        "retryable": len(retryable),
        "statuses": dict(statuses),
        "malformed": malformed,
        "cross_case": cross_case,
        "suspicious_ok": suspicious_ok,
        "incomplete_parser_audit": incomplete_parser_audit,
        "post_terminal_receipts": post_terminal_receipts,
        "fatal_runtime": fatal_runtime,
        "age_seconds": round(age, 1) if age is not None else None,
    }


def main() -> int:
    cells = {cell_id: inspect(OUT_DIR / filename) for cell_id, filename in CELLS}
    critical = []
    for cell_id, cell in cells.items():
        if cell["malformed"]:
            critical.append(f"{cell_id}: malformed JSONL={cell['malformed']}")
        if cell["cross_case"]:
            critical.append(f"{cell_id}: cross-case traces={cell['cross_case']}")
        if cell["incomplete_parser_audit"]:
            critical.append(
                f"{cell_id}: incomplete parser audit={cell['incomplete_parser_audit']}"
            )
        if cell["post_terminal_receipts"]:
            critical.append(
                f"{cell_id}: receipts written after terminal="
                f"{cell['post_terminal_receipts']}"
            )
        if cell["fatal_runtime"]:
            critical.append(
                f"{cell_id}: swallowed fatal runtime failures="
                f"{cell['fatal_runtime']}"
            )
        if (
            cell["settled"] >= 2
            and cell["statuses"].get("ok", 0) == 0
            and cell["statuses"].get("parser_error", 0) == cell["settled"]
        ):
            critical.append(
                f"{cell_id}: semantic collapse, first {cell['settled']} "
                "settled cases contain zero valid predictions"
            )
        if cell["unique"] > 100:
            critical.append(f"{cell_id}: unique cases exceeds target={cell['unique']}")

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "settled_total": sum(cell["settled"] for cell in cells.values()),
        "target_total": 500,
        "critical": critical,
        "cells": cells,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "monitor_history.jsonl").open("a") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    (LOG_DIR / "monitor_latest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 2 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())

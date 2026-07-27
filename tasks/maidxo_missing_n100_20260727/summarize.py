#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
ROOT = TASK_DIR.parents[1]
LOG_DIR = ROOT / "logs" / "maidxo_missing_n100_20260727"
STATE_DIR = LOG_DIR / "state"
OUT_DIR = ROOT / "data" / "round2" / "phase4a"

CELLS = [
    ("pp_gpt5", "PP-Store", "GPT-5",
     "predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl", 2000),
    ("rarearena_v4flash", "RareArena", "DS V4-Flash",
     "predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl", 2000),
    ("rarearena_gpt5", "RareArena", "GPT-5",
     "predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl", 2000),
    ("rarebench_v4flash", "RareBench", "DS V4-Flash",
     "predictions_rarebench_maidxo_deepseek_deepseek-v4-flash.jsonl", 1122),
    ("rarebench_gpt5", "RareBench", "GPT-5",
     "predictions_rarebench_maidxo_openai_gpt-5.jsonl", 1122),
]


def read_meta(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def inspect_predictions(path: Path) -> dict:
    rows: list[dict] = []
    if path.exists():
        for line in path.open(errors="replace"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    best: dict[str, dict] = {}
    for row in rows:
        cid = row.get("case_id")
        if cid is None:
            continue
        previous = best.get(str(cid))
        if previous is None or (
            row.get("status") == "ok" and previous.get("status") != "ok"
        ):
            best[str(cid)] = row
    statuses = Counter(str(row.get("status")) for row in best.values())
    actual_cost = sum(
        float((row.get("cost") or {}).get("cost_usd") or 0.0) for row in rows
    )
    simulated_clinical_cost = sum(
        float(
            (row.get("extra") or {}).get(
                "maidxo_simulated_clinical_cost_usd",
                (row.get("extra") or {}).get("simulated_cost_usd", 0.0),
            )
            or 0.0
        )
        for row in rows
    )
    latency_ms = sum(int(row.get("total_latency_ms") or 0) for row in rows)
    fallback_exact = sum(
        str(
            (row.get("extra") or {}).get("maidxo_raw_final_diagnosis") or ""
        )
        == "Unable to establish definitive diagnosis - further evaluation needed"
        for row in best.values()
    )
    return {
        "raw_receipts": len(rows),
        "unique_cases": len(best),
        "n_ok": statuses.get("ok", 0),
        "statuses": dict(statuses),
        "actual_cost_usd": actual_cost,
        "simulated_clinical_cost_usd": simulated_clinical_cost,
        "receipt_latency_hours": latency_ms / 3_600_000,
        "fallback_exact": fallback_exact,
        "fragment_or_other": len(best) - fallback_exact,
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    now_epoch = int(now.timestamp())
    results = []
    for cell_id, dataset, backbone, filename, target in CELLS:
        observed = inspect_predictions(OUT_DIR / filename)
        meta = read_meta(STATE_DIR / f"{cell_id}.meta")
        recorded_wall_seconds = int(meta.get("wall_seconds", "0") or 0)
        start_epoch = int(meta.get("start_epoch", "0") or 0)
        wall_seconds = (
            recorded_wall_seconds
            if recorded_wall_seconds > 0
            else max(0, now_epoch - start_epoch) if start_epoch else 0
        )
        n = observed["unique_cases"]
        scale = target / n if n else None
        results.append({
            "cell_id": cell_id,
            "dataset": dataset,
            "agent": "maidxo",
            "backbone": backbone,
            "pilot_n": 100,
            "full_target_n": target,
            "done": (STATE_DIR / f"{cell_id}.done").exists(),
            "wall_seconds": wall_seconds,
            **observed,
            "estimated_full_cost_usd": (
                observed["actual_cost_usd"] * scale if scale else None
            ),
            "estimated_full_wall_hours_same_cell": (
                wall_seconds * scale / 3600 if scale else None
            ),
        })

    starts = [
        int(read_meta(STATE_DIR / f"{cell_id}.meta").get("start_epoch", "0") or 0)
        for cell_id, *_ in CELLS
    ]
    ends = [
        int(read_meta(STATE_DIR / f"{cell_id}.meta").get("end_epoch", "0") or 0)
        for cell_id, *_ in CELLS
    ]
    valid_starts = [value for value in starts if value > 0]
    valid_ends = [value for value in ends if value > 0]
    campaign_wall_seconds = (
        max(valid_ends) - min(valid_starts)
        if valid_starts and valid_ends
        else 0
    )
    payload = {
        "generated_utc": now.isoformat(),
        "method": (
            "Linear extrapolation from N=100 observed receipts. Cost includes "
            "all written retry/failure receipts. Time assumes identical "
            "supervisor-selected concurrency and service conditions. For an "
            "in-progress cell, observed wall time runs from its current "
            "state metadata start time to summary generation."
        ),
        "campaign_wall_seconds": campaign_wall_seconds,
        "cells": results,
    }
    (TASK_DIR / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )

    lines = [
        "# MAI-DxO missing-cell N=100 status",
        "",
        f"Generated: {payload['generated_utc']}",
        "",
        "| Dataset | Backbone | Done | Unique/100 | OK | Cost USD | Wall h | "
        "Est. full N | Est. full cost | Est. cell wall h |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results:
        full_cost = row["estimated_full_cost_usd"]
        full_wall = row["estimated_full_wall_hours_same_cell"]
        lines.append(
            f"| {row['dataset']} | {row['backbone']} | "
            f"{'yes' if row['done'] else 'no'} | {row['unique_cases']}/100 | "
            f"{row['n_ok']} | ${row['actual_cost_usd']:.4f} | "
            f"{row['wall_seconds']/3600:.2f} | {row['full_target_n']} | "
            f"{'$%.2f' % full_cost if full_cost is not None else '—'} | "
            f"{'%.1f' % full_wall if full_wall is not None else '—'} |"
        )
    actual_cost = sum(row["actual_cost_usd"] for row in results)
    estimated_cost = sum(
        row["estimated_full_cost_usd"] or 0.0 for row in results
    )
    estimated_cell_hours = sum(
        row["estimated_full_wall_hours_same_cell"] or 0.0 for row in results
    )
    parser_errors = sum(
        row["statuses"].get("parser_error", 0) for row in results
    )
    fallback_exact = sum(row["fallback_exact"] for row in results)
    fragment_or_other = sum(row["fragment_or_other"] for row in results)
    simulated_clinical_cost = sum(
        row["simulated_clinical_cost_usd"] for row in results
    )
    lines.extend([
        "",
        f"- Auditable outcome: **0/500 usable predictions; "
        f"{parser_errors}/500 parser errors**.",
        f"- Raw final outputs: **{fallback_exact}** exact forced-fallback "
        f"strings and **{fragment_or_other}** non-diagnostic fragments/other "
        "outputs; strict post-processing accepted none as a disease.",
        f"- Observed clean-campaign wall time: "
        f"**{campaign_wall_seconds / 3600:.2f} h** "
        "(includes the workstation sleep interval).",
        f"- Estimated inference cost so far: **${actual_cost:.4f}**.",
        f"- MAI-DxO simulated clinical visit/test cost: "
        f"**${simulated_clinical_cost:,.2f}** (not API spend).",
        f"- Linear estimated full-target cost: **${estimated_cost:.2f}**.",
        f"- Rough full-target serial cell-hours: **{estimated_cell_hours:.1f} h**.",
        "- Full-target extrapolations are planning bounds only and should not "
        "be used to authorize a full run until MAI-DxO's upstream structured "
        "differential extraction is repaired and passes a small smoke test.",
        "- Multi-cell parallel wall time will be lower than serial cell-hours.",
        "- Receipt inference cost is estimated from captured text because "
        "MAI-DxO does not expose gateway token usage. Its separate simulated "
        "clinical visit/test cost is retained in the JSON summary and must "
        "not be interpreted as API spend.",
        "",
        "Failures, parser errors, and timeouts remain in the attempted "
        "denominator. Estimates are planning values, not billing guarantees.",
    ])
    (TASK_DIR / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Score and summarize the audited five-cell MAI-DxO N=100 run."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.metrics.cross_map import (  # noqa: E402
    gold_hit_with_crossmap,
    gold_hit_with_variants,
)
from scripts.phase4a_runner import (  # noqa: E402
    load_phenopacket_store,
    load_rarearena_rds,
    load_rarebench_stratified,
)

CELLS = {
    "pp_gpt5": (
        "Phenopacket Store",
        "GPT-5",
        load_phenopacket_store,
        "predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl",
    ),
    "rarearena_v4flash": (
        "RareArena RDS",
        "DeepSeek V4-Flash",
        load_rarearena_rds,
        "predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl",
    ),
    "rarearena_gpt5": (
        "RareArena RDS",
        "GPT-5",
        load_rarearena_rds,
        "predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl",
    ),
    "rarebench_v4flash": (
        "RareBench",
        "DeepSeek V4-Flash",
        load_rarebench_stratified,
        "predictions_rarebench_maidxo_deepseek_deepseek-v4-flash.jsonl",
    ),
    "rarebench_gpt5": (
        "RareBench",
        "GPT-5",
        load_rarebench_stratified,
        "predictions_rarebench_maidxo_openai_gpt-5.jsonl",
    ),
}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, int((len(ordered) - 1) * q))
    return ordered[index]


def summarize_cell(path: Path, loader) -> dict:
    rows = [json.loads(line) for line in path.open() if line.strip()]
    cases = loader(n=100)
    expected = {str(case.case_id): case for case in cases}
    by_id = {str(row["case_id"]): row for row in rows}
    if len(rows) != 100 or len(by_id) != 100 or set(by_id) != set(expected):
        raise ValueError(
            f"{path}: rows={len(rows)}, unique={len(by_id)}, "
            f"missing={len(set(expected) - set(by_id))}, "
            f"unexpected={len(set(by_id) - set(expected))}"
        )

    h1_strict = h5_strict = h1_variant = h5_variant = 0
    for case_id, case in expected.items():
        row = by_id[case_id]
        predictions = row.get("ranked_predictions") or []
        variants = (row.get("extra") or {}).get(
            "ranked_predictions_variants"
        ) or []
        if predictions and gold_hit_with_crossmap(
            predictions[0], case.gold_label
        ):
            h1_strict += 1
        if any(
            gold_hit_with_crossmap(value, case.gold_label)
            for value in predictions[:5]
        ):
            h5_strict += 1
        if variants:
            if variants[0] and gold_hit_with_variants(
                variants[0], case.gold_label
            ):
                h1_variant += 1
            if any(
                values and gold_hit_with_variants(values, case.gold_label)
                for values in variants[:5]
            ):
                h5_variant += 1
        else:
            h1_variant += int(
                bool(
                    predictions
                    and gold_hit_with_crossmap(
                        predictions[0], case.gold_label
                    )
                )
            )
            h5_variant += int(
                any(
                    gold_hit_with_crossmap(value, case.gold_label)
                    for value in predictions[:5]
                )
            )

    latency_seconds = [
        float(row.get("total_latency_ms") or 0) / 1000 for row in rows
    ]
    extension_ids = {str(case.case_id) for case in cases[10:]}
    extension_rows = [by_id[case_id] for case_id in extension_ids]
    extension_starts = [
        value
        for value in (
            parse_time(row.get("started_at")) for row in extension_rows
        )
        if value is not None
    ]
    extension_finishes = [
        value
        for value in (
            parse_time(row.get("finished_at")) for row in extension_rows
        )
        if value is not None
    ]
    receipt_cost = sum(
        float((row.get("cost") or {}).get("cost_usd") or 0) for row in rows
    )
    simulated_clinical_cost = sum(
        float(
            (row.get("extra") or {}).get(
                "maidxo_simulated_clinical_cost_usd"
            )
            or 0
        )
        for row in rows
    )
    abstentions = [
        str(row["case_id"])
        for row in rows
        if row.get("status") == "parser_error"
    ]
    return {
        "rows": 100,
        "statuses": dict(Counter(str(row.get("status")) for row in rows)),
        "terminal_model_abstentions": abstentions,
        "attempted_denominator": 100,
        "hits_r1_strict": h1_strict,
        "hits_r5_strict": h5_strict,
        "hits_r1_variant": h1_variant,
        "hits_r5_variant": h5_variant,
        "R1_strict_attempted": round(h1_strict / 100, 4),
        "R5_strict_attempted": round(h5_strict / 100, 4),
        "R1_variant_attempted": round(h1_variant / 100, 4),
        "R5_variant_attempted": round(h5_variant / 100, 4),
        "latency_sum_hours": round(sum(latency_seconds) / 3600, 4),
        "latency_median_seconds": round(
            statistics.median(latency_seconds), 3
        ),
        "latency_p95_seconds": round(
            percentile(latency_seconds, 0.95), 3
        ),
        "receipt_side_cost_estimate_usd": round(receipt_cost, 6),
        "simulated_clinical_cost_usd": round(
            simulated_clinical_cost, 2
        ),
        "n100_extension_started_at": (
            min(extension_starts).isoformat() if extension_starts else None
        ),
        "n100_extension_finished_at": (
            max(extension_finishes).isoformat() if extension_finishes else None
        ),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase4a-dir",
        type=Path,
        default=ROOT / "data" / "round2" / "phase4a",
    )
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    cells = {}
    for cell_id, (dataset, backbone, loader, filename) in CELLS.items():
        summary = summarize_cell(args.phase4a_dir / filename, loader)
        summary.update(
            {
                "dataset": dataset,
                "backbone": backbone,
                "filename": filename,
            }
        )
        cells[cell_id] = summary

    starts = [
        parse_time(cell["n100_extension_started_at"])
        for cell in cells.values()
        if cell["n100_extension_started_at"]
    ]
    finishes = [
        parse_time(cell["n100_extension_finished_at"])
        for cell in cells.values()
        if cell["n100_extension_finished_at"]
    ]
    overall_start = min(starts) if starts else None
    overall_finish = max(finishes) if finishes else None
    payload = {
        "scope": "MAI-DxO five missing cells, deterministic N=100 each",
        "total_case_cells": 500,
        "total_ok": sum(
            cell["statuses"].get("ok", 0) for cell in cells.values()
        ),
        "total_terminal_model_abstentions": sum(
            len(cell["terminal_model_abstentions"])
            for cell in cells.values()
        ),
        "n100_extension_wall_clock_hours": (
            round((overall_finish - overall_start).total_seconds() / 3600, 4)
            if overall_start and overall_finish
            else None
        ),
        "aggregate_case_latency_hours": round(
            sum(cell["latency_sum_hours"] for cell in cells.values()), 4
        ),
        "receipt_side_cost_estimate_usd": round(
            sum(
                cell["receipt_side_cost_estimate_usd"]
                for cell in cells.values()
            ),
            6,
        ),
        "simulated_clinical_cost_usd": round(
            sum(
                cell["simulated_clinical_cost_usd"]
                for cell in cells.values()
            ),
            2,
        ),
        "cost_note": (
            "cost_usd is the harness token-price estimate, not an AIHubMix "
            "billing receipt. MAI-DxO does not expose complete LiteLLM usage, "
            "so this estimate may omit internal panel calls. "
            "maidxo_simulated_clinical_cost_usd is a simulated care-resource "
            "cost, not API spend."
        ),
        "scoring_note": (
            "All rates use the fixed attempted denominator N=100 per cell. "
            "Explicit model abstentions remain terminal misses."
        ),
        "cells": cells,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )

    lines = [
        "# MAI-DxO N=100 final results",
        "",
        "All rates use the fixed attempted denominator of 100 cases per cell; "
        "explicit model abstentions count as misses.",
        "",
        "| Dataset | Backbone | Terminal | Abstain | R@1 variant | R@5 variant | Median latency | Receipt cost estimate |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in cells.values():
        lines.append(
            f"| {cell['dataset']} | {cell['backbone']} | 100/100 | "
            f"{len(cell['terminal_model_abstentions'])} | "
            f"{cell['R1_variant_attempted']:.3f} | "
            f"{cell['R5_variant_attempted']:.3f} | "
            f"{cell['latency_median_seconds']:.1f}s | "
            f"${cell['receipt_side_cost_estimate_usd']:.4f} |"
        )
    lines += [
        "",
        f"- Total terminal receipts: **{payload['total_case_cells']}/500**",
        f"- Normal predictions: **{payload['total_ok']}**",
        "- Explicit model abstentions: "
        f"**{payload['total_terminal_model_abstentions']}**",
        "- N=100 extension wall clock: "
        f"**{payload['n100_extension_wall_clock_hours']:.2f} h**",
        "- Aggregate per-case latency: "
        f"**{payload['aggregate_case_latency_hours']:.2f} h**",
        "- Summed receipt-side cost estimate: "
        f"**${payload['receipt_side_cost_estimate_usd']:.4f}**",
        "- MAI-DxO simulated clinical-resource cost: "
        f"**${payload['simulated_clinical_cost_usd']:,.0f}**",
        "",
        "The cost estimate is not an AIHubMix invoice and may omit internal "
        "panel calls because MAI-DxO does not expose complete LiteLLM usage. "
        "The simulated clinical cost is also not API spend.",
        "",
        "## Receipt hashes",
        "",
        "```text",
    ]
    for cell in cells.values():
        lines.append(f"{cell['sha256']}  {cell['filename']}")
    lines += ["```", ""]
    args.out_md.write_text("\n".join(lines))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build leakage-controlled MIMIC-IV structured-EHR experiment arms.

This script deliberately does *not* describe the current MIMIC slice as a
clinical-note or phenotype-based diagnosis benchmark.  The source cohort was
constructed from ICD-10 diagnoses and contains no MIMIC-IV-Note text.

For each admission it creates three paired inputs:

1. ``title_selection``: ICD long titles, including the target-bearing title.
   This measures rare-disease selection from a coded problem list.
2. ``code_selection``: ICD codes only.  This measures code knowledge plus
   ICD-to-Orphanet normalization without a direct disease-name cue.
3. ``context_only``: target-bearing ICD entries removed.  This negative-control
   arm measures how much signal remains in co-occurring rare-disease codes.

Outputs remain under ``data/`` (gitignored) because case-level MIMIC-derived
records are credentialed.  The printed aggregate manifest is safe to copy into
an audit report; review the PhysioNet DUA before sharing any generated JSONL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ARM_NAMES = ("title_selection", "code_selection", "context_only")


def _stable_unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _hits(case: dict[str, Any]) -> list[dict[str, Any]]:
    hits = case.get("metadata", {}).get("all_orpha_hits") or []
    return [h for h in hits if isinstance(h, dict)]


def target_hits(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ICD entries that map to the case's gold ORPHA label."""
    gold_orpha = case.get("gold_label", {}).get("orphanet_id")
    return [h for h in _hits(case) if h.get("orpha_id") == gold_orpha]


def build_arm(case: dict[str, Any], arm: str) -> dict[str, Any]:
    if arm not in ARM_NAMES:
        raise ValueError(f"unknown arm: {arm}")

    all_hits = _hits(case)
    target = target_hits(case)
    target_pairs = {
        (str(h.get("icd_code") or ""), str(h.get("icd_title") or ""))
        for h in target
    }

    if arm == "title_selection":
        items = _stable_unique(str(h.get("icd_title") or "") for h in all_hits)
        instruction = (
            "Select the ONE Orphanet-listed rare disease that is the primary "
            "coding focus from these ICD-10 long titles."
        )
    elif arm == "code_selection":
        items = _stable_unique(str(h.get("icd_code") or "") for h in all_hits)
        instruction = (
            "Select the ONE Orphanet-listed rare disease that is the primary "
            "coding focus from these ICD-10 codes. Return a disease name or "
            "ORPHA identifier."
        )
    else:
        retained = [
            h
            for h in all_hits
            if (str(h.get("icd_code") or ""), str(h.get("icd_title") or ""))
            not in target_pairs
        ]
        items = _stable_unique(str(h.get("icd_title") or "") for h in retained)
        instruction = (
            "Infer the primary rare disease, if possible, from the remaining "
            "co-occurring coded conditions after the target diagnosis entry "
            "has been removed. Return a disease name or ORPHA identifier."
        )

    demographics = case.get("demographics") or {}
    return {
        "case_id": case.get("case_id"),
        "arm": arm,
        "age_at_diagnosis_years": demographics.get("age_at_diagnosis_years"),
        "sex": demographics.get("sex"),
        "items": items,
        "instruction": instruction,
        "gold_orpha": case.get("gold_label", {}).get("orphanet_id"),
        "gold_disease": case.get("gold_label", {}).get("disease_name"),
        "primary_relation": case.get("metadata", {}).get("primary_relation"),
        "target_entry_count": len(target_pairs),
    }


def iter_cases(path: Path) -> Iterable[dict[str, Any]]:
    with path.open() as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(input_path: Path, output_path: Path | None) -> dict[str, Any]:
    counts = Counter()
    relation_counts = Counter()
    disease_ids: set[str] = set()
    arm_empty = Counter()
    target_missing = 0
    writer = output_path.open("w") if output_path else None
    try:
        for case in iter_cases(input_path):
            counts["cases"] += 1
            gold_orpha = case.get("gold_label", {}).get("orphanet_id")
            if gold_orpha:
                disease_ids.add(gold_orpha)
            relation_counts[str(case.get("metadata", {}).get("primary_relation"))] += 1
            if not target_hits(case):
                target_missing += 1
            for arm in ARM_NAMES:
                row = build_arm(case, arm)
                counts[f"rows_{arm}"] += 1
                if not row["items"]:
                    arm_empty[arm] += 1
                if writer:
                    writer.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if writer:
            writer.close()

    return {
        "input": str(input_path),
        "input_sha256": sha256(input_path),
        "n_cases": counts["cases"],
        "n_unique_gold_orpha": len(disease_ids),
        "primary_relation_counts": dict(sorted(relation_counts.items())),
        "n_cases_without_target_link": target_missing,
        "rows_per_arm": {arm: counts[f"rows_{arm}"] for arm in ARM_NAMES},
        "empty_input_by_arm": {arm: arm_empty[arm] for arm in ARM_NAMES},
        "output": str(output_path) if output_path else None,
        "design_version": "mimic-structured-ablation-v1",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional credentialed JSONL output (keep under gitignored data/).",
    )
    args = parser.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(args.input, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

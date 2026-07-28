#!/usr/bin/env python3
"""Compact and normalize the nine Phase 4a receipts after the coverage run."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from run_yutian import CELLS, OUT_DIR, STATE_DIR, TERMINAL

FIXED_PREFIX_DIR = STATE_DIR / "fixed_prefix"
OVERRIDES = {
    "mx_pp_flash": [FIXED_PREFIX_DIR / "pp_flash_head78.jsonl"],
    "mx_pp_gem": [FIXED_PREFIX_DIR / "pp_gem_head100.jsonl"],
    "mx_ra_gem": [FIXED_PREFIX_DIR / "ra_gem_head100.jsonl"],
    "dr_ra_gpt5": [FIXED_PREFIX_DIR / "dr_ra_gpt5_fixed200.jsonl"],
}


def read_rows(paths: list[Path]) -> tuple[list[dict], int]:
    rows: list[dict] = []
    malformed = 0
    for path in paths:
        for raw in path.open(errors="replace"):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
                row["_finalize_source"] = str(path)
                rows.append(row)
            except json.JSONDecodeError:
                malformed += 1
    if malformed:
        raise RuntimeError(f"{paths}: {malformed} malformed rows")
    return rows, malformed


def compact(
    path: Path,
    expected_backbone: str,
    archive_dir: Path,
    override_paths: list[Path],
) -> dict:
    sources = [path, *override_paths]
    rows, _ = read_rows(sources)
    override_names = {str(source) for source in override_paths}
    override_case_ids = {
        str(row["case_id"])
        for row in rows
        if row.get("_finalize_source") in override_names
    }
    attempts: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        attempts.setdefault(str(row["case_id"]), []).append(row)

    chosen: list[dict] = []
    recovered = 0
    for case_rows in attempts.values():
        override_rows = [
            row
            for row in case_rows
            if row.get("_finalize_source") in override_names
        ]
        candidates = override_rows or case_rows
        selected = candidates[0]
        for row in candidates:
            if row.get("status") in TERMINAL:
                selected = row
                break
        if selected is not candidates[0]:
            recovered += 1
        selected.pop("_finalize_source", None)
        selected["backbone_id"] = expected_backbone

        predictions = list(selected.get("ranked_predictions") or [])
        confidences = list(selected.get("confidence_scores") or [])
        variants = list(
            (selected.get("extra") or {}).get(
                "ranked_predictions_variants"
            )
            or []
        )
        keep: list[int] = []
        seen: set[str] = set()
        for index, prediction in enumerate(predictions):
            key = " ".join(str(prediction).split()).casefold()
            if key not in seen:
                seen.add(key)
                keep.append(index)
        if len(keep) != len(predictions):
            selected["ranked_predictions"] = [
                predictions[index] for index in keep
            ]
            if len(confidences) == len(predictions):
                selected["confidence_scores"] = [
                    confidences[index] for index in keep
                ]
            if len(variants) == len(predictions):
                selected.setdefault("extra", {})[
                    "ranked_predictions_variants"
                ] = [variants[index] for index in keep]
        chosen.append(selected)

    archive_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        shutil.copy2(
            source,
            archive_dir / f"{path.stem}__{source.parent.name}__{source.name}",
        )
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w") as handle:
            for row in chosen:
                handle.write(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return {
        "input_rows": len(rows),
        "output_rows": len(chosen),
        "duplicate_attempts_removed": len(rows) - len(chosen),
        "recovered_with_first_terminal": recovered,
        "override_files": [str(source) for source in override_paths],
        "override_case_ids": len(override_case_ids),
    }


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = STATE_DIR / f"precompact_{stamp}"
    report = {}
    for cell in CELLS:
        path = OUT_DIR / cell.filename
        overrides = OVERRIDES.get(cell.cell_id, [])
        missing = [source for source in overrides if not source.exists()]
        if missing:
            raise RuntimeError(
                f"{cell.cell_id}: missing required fixed-code overrides: "
                f"{missing}"
            )
        report[cell.cell_id] = compact(
            path, cell.backbone, archive_dir, overrides
        )
    report_path = STATE_DIR / "finalize_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Recover DeepRare numbered-list predictions from retained patient JSON."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.agents.deeprare import parse_deeprare_final_diagnois  # noqa: E402

FILES = (
    ROOT
    / "data/round2/phase4a"
    / "predictions_phenopacket_store_deeprare_openai_gpt-5.jsonl",
    ROOT
    / "data/round2/phase4a"
    / "predictions_rarebench_deeprare_openai_gpt-5.jsonl",
)


def recover(path: Path, archive: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    changed = []
    unresolved = []
    for row in rows:
        if row.get("status") != "ok" or row.get("ranked_predictions"):
            continue
        patient_path = Path(
            (row.get("extra") or {}).get("deeprare_patient_json_path", "")
        )
        if not patient_path.exists():
            unresolved.append(str(row.get("case_id")))
            continue
        patient = json.loads(patient_path.read_text(encoding="utf-8-sig"))
        final = (
            patient.get("final_diagnois")
            or patient.get("first_round_result")
            or ""
        )
        predictions = parse_deeprare_final_diagnois(final)
        if not predictions:
            row["status"] = "parser_error"
            row["error_message"] = (
                "DeepRare final response contained no parseable ranked diagnoses."
            )
            row["raw_response_excerpt"] = final[:2000]
            continue
        row["ranked_predictions"] = predictions
        row["raw_response_excerpt"] = final[:2000]
        changed.append(str(row["case_id"]))

    shutil.copy2(path, archive / path.name)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w") as handle:
            for row in rows:
                handle.write(
                    json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return {"recovered": changed, "unresolved": unresolved}


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = (
        ROOT / "logs/coverage_10pct_20260728" / f"pre_numbered_recovery_{stamp}"
    )
    archive.mkdir(parents=True)
    report = {str(path.relative_to(ROOT)): recover(path, archive) for path in FILES}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(not item["unresolved"] for item in report.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())

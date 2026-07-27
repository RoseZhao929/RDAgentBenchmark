#!/usr/bin/env python3
"""Mechanically deduplicate aligned prediction fields in a receipt JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    changed = 0
    output: list[str] = []
    for line in args.source.open():
        row = json.loads(line)
        predictions = list(row.get("ranked_predictions") or [])
        confidences = list(row.get("confidence_scores") or [])
        extra = row.get("extra") or {}
        variants = list(extra.get("ranked_predictions_variants") or [])
        keep: list[int] = []
        seen: set[str] = set()
        for index, prediction in enumerate(predictions):
            normalized = " ".join(str(prediction).split()).casefold()
            if normalized in seen:
                changed += 1
                continue
            seen.add(normalized)
            keep.append(index)
        if len(keep) != len(predictions):
            row["ranked_predictions"] = [predictions[index] for index in keep]
            if len(confidences) == len(predictions):
                row["confidence_scores"] = [
                    confidences[index] for index in keep
                ]
            if len(variants) == len(predictions):
                extra["ranked_predictions_variants"] = [
                    variants[index] for index in keep
                ]
            extra["receipt_normalization"] = {
                "operation": "stable case-insensitive prediction deduplication",
                "removed": len(predictions) - len(keep),
            }
            row["extra"] = extra
        output.append(json.dumps(row, ensure_ascii=False))
    args.destination.write_text("\n".join(output) + "\n")
    print(json.dumps({"removed_duplicates": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

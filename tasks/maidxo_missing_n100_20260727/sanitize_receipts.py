#!/usr/bin/env python3
"""Deterministically remove non-diagnosis MAI-DxO predictions in-place.

The model call, raw final diagnosis, reasoning trace, latency, and cost remain
unchanged. An ``ok`` receipt whose complete ranked list is noise is reclassified
as ``parser_error`` so attempted-denominator scoring remains auditable without
paying for or repeating the completed call.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.agents.maidxo import (  # noqa: E402
    _accept_orpha_mapping,
    _clean_for_fuzzy,
    _is_noise_candidate,
)
from harness.pmc_oa.orphanet import map_diagnosis, parse_orphadata  # noqa: E402


def sanitize(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0

    rows: list[dict] = []
    malformed = 0
    with path.open(errors="replace") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    if malformed:
        raise RuntimeError(f"refusing to rewrite {path}: {malformed} malformed lines")

    changed = 0
    reclassified = 0
    tables = parse_orphadata()
    for row in rows:
        extra = row.setdefault("extra", {})
        migrated_cost_key = False
        if "simulated_cost_usd" in extra:
            extra.setdefault(
                "maidxo_simulated_clinical_cost_usd",
                extra.pop("simulated_cost_usd"),
            )
            changed += 1
            migrated_cost_key = True
        if row.get("status") != "ok":
            continue
        predictions = [str(x) for x in row.get("ranked_predictions") or []]
        confidences = list(row.get("confidence_scores") or [])
        raw_differential = extra.get("maidxo_raw_differential") or {}
        raw_text = "\n".join(
            [
                str(extra.get("maidxo_raw_final_diagnosis") or ""),
                *(
                    [str(x) for x in raw_differential.keys()]
                    if isinstance(raw_differential, dict)
                    else []
                ),
            ]
        )
        explicit_ids = {
            match.upper()
            for match in re.findall(
                r"\b(?:ORPHA|OMIM|CCRD):\d+\b", raw_text, re.I
            )
        }
        invalid_fuzzy: set[str] = set()
        invalid_fuzzy_audit: list[dict] = []
        for audit in extra.get("maidxo_fuzzy_fallback") or []:
            if not isinstance(audit, dict) or audit.get("type") != "fuzzy":
                continue
            source = str(audit.get("input") or "")
            query = _clean_for_fuzzy(source) or source
            mapped = map_diagnosis(query, tables, return_top_k=5)
            if not mapped.get("orpha_id") and query != source:
                query = source
                mapped = map_diagnosis(query, tables, return_top_k=5)
            accepted = _accept_orpha_mapping(query, mapped)
            audit["matched_name"] = mapped.get("matched_name")
            audit["strict_accepted"] = accepted
            orpha = str(audit.get("orpha") or mapped.get("orpha_id") or "").upper()
            if orpha and not accepted and orpha not in explicit_ids:
                invalid_fuzzy.add(orpha)
                invalid_fuzzy_audit.append(
                    {
                        "rank": audit.get("rank"),
                        "input": source,
                        "orpha": orpha,
                        "matched_name": mapped.get("matched_name"),
                        "score": mapped.get("score"),
                    }
                )
        kept: list[str] = []
        kept_conf: list[float] = []
        dropped: list[str] = []
        for index, prediction in enumerate(predictions):
            if (
                _is_noise_candidate(prediction)
                or prediction.upper() in invalid_fuzzy
            ):
                dropped.append(prediction)
            else:
                kept.append(prediction)
                if index < len(confidences):
                    kept_conf.append(confidences[index])
        if not dropped:
            continue

        if not migrated_cost_key:
            changed += 1
        extra["maidxo_posthoc_noise_filtered"] = dropped
        if invalid_fuzzy_audit:
            extra["maidxo_posthoc_invalid_fuzzy_filtered"] = invalid_fuzzy_audit
        extra.setdefault("maidxo_original_status", "ok")
        row["ranked_predictions"] = kept
        row["confidence_scores"] = kept_conf

        variants = extra.get("ranked_predictions_variants")
        if isinstance(variants, list):
            cleaned_variants = []
            for group in variants:
                if isinstance(group, list):
                    clean = [
                        str(x)
                        for x in group
                        if (
                            not _is_noise_candidate(str(x))
                            and str(x).upper() not in invalid_fuzzy
                        )
                    ]
                    if clean:
                        cleaned_variants.append(clean)
            extra["ranked_predictions_variants"] = cleaned_variants

        if not kept:
            reclassified += 1
            row["status"] = "parser_error"
            row["error_message"] = (
                "All ranked predictions filtered as non-diagnostic vignette, "
                "vital-sign, laboratory, or sentence-fragment output."
            )

    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(fd, "w") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
    return changed, reclassified


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} RECEIPTS.jsonl", file=sys.stderr)
        return 2
    path = Path(sys.argv[1]).resolve()
    changed, reclassified = sanitize(path)
    print(
        f"[sanitize] {path.name}: changed={changed} "
        f"reclassified_parser_error={reclassified}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

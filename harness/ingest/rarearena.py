"""Ingest adapter: RareArena RDS / RDC JSONL -> CanonicalCase.

Source: data/rarearena/benchmark_data/{RDS,RDC}_benchmark.jsonl  (subsampled)
   or:  data/rarearena/benchmark_data/{RDS,RDC}.json              (full)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Literal, Optional

from harness.canonical_case import (
    CanonicalCase,
    Demographics,
    GoldLabel,
    Sex,
)

RareArenaSubset = Literal["RDS", "RDC"]


def _parse_sex(s: Optional[str]) -> Optional[Sex]:
    if not s:
        return None
    s = s.upper()
    if s in ("M", "MALE"):
        return "male"
    if s in ("F", "FEMALE"):
        return "female"
    return "unknown"


def _parse_age(age_field) -> Optional[float]:
    """Parse RareArena age field: [[38.0, "year"], ...] or None.

    First entry typically the most informative. Convert to years.
    """
    if not age_field or not isinstance(age_field, list) or len(age_field) == 0:
        return None
    entry = age_field[0]
    if not isinstance(entry, list) or len(entry) != 2:
        return None
    value, unit = entry
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    unit = (unit or "").lower()
    if unit.startswith("year"):
        return v
    if unit.startswith("month"):
        return v / 12.0
    if unit.startswith("week"):
        return v / 52.0
    if unit.startswith("day"):
        return v / 365.25
    return v  # default assume years


def rarearena_record_to_canonical(
    record: dict, subset: RareArenaSubset
) -> CanonicalCase:
    orpha_raw = record.get("Orpha_id")
    orpha_id = f"ORPHA:{orpha_raw}" if orpha_raw else None

    gold = GoldLabel(
        omim_id=None,
        orphanet_id=orpha_id,
        ccrd_id=None,
        disease_name=record.get("Orpha_name") or record.get("diagnosis"),
        hgnc_gene_id=None,
    )
    if not gold.has_any_id():
        raise ValueError(
            f"RareArena record {record.get('_id', '?')} has no Orpha_id; skip."
        )

    return CanonicalCase(
        case_id=str(record.get("_id", "UNKNOWN")),
        source_dataset="rarearena",
        source_split=subset,
        language="en",
        demographics=Demographics(
            age_at_onset_years=_parse_age(record.get("age")),
            sex=_parse_sex(record.get("gender")),
        ),
        free_text_vignette=record.get("case_report"),
        synthetic_vignette=None,
        gold_hpo_terms=[],   # RareArena has no native HPO
        variants=[],
        family=None,
        gold_label=gold,
        metadata={
            "publication_date": record.get("pub_date"),
            "raw_diagnosis": record.get("diagnosis"),
        },
    )


def ingest_rarearena(
    jsonl_path: Path | str,
    subset: RareArenaSubset,
    limit: Optional[int] = None,
) -> Iterator[CanonicalCase]:
    """Yield CanonicalCase from a RareArena JSONL file.

    `subset` must be one of "RDS" / "RDC" (this becomes source_split).
    """
    import sys

    path = Path(jsonl_path)
    count = 0
    with path.open() as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                yield rarearena_record_to_canonical(record, subset=subset)
                count += 1
                if limit and count >= limit:
                    return
            except Exception as e:
                print(
                    f"[ingest_rarearena] SKIP {path}:{lineno}: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr,
                )


__all__ = ["rarearena_record_to_canonical", "ingest_rarearena", "RareArenaSubset"]

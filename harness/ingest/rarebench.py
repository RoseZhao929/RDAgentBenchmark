"""Ingest adapter: RareBench (HuggingFace format) -> CanonicalCase.

Source: data/rarebench_hf/data_unzipped/data/{RAMEDIS,MME,HMS,LIRICAL,PUMCH_ADM}.jsonl

Per-record format (verified 2026-05-11):
    {
      "Phenotype": ["HP:0001522", "HP:0001942", ...],
      "RareDisease": ["OMIM:251000", "ORPHA:27", "CCRD:71"],
      "Department": null   // only PUMCH_ADM populates this
    }

Diseases carried as side-by-side OMIM / ORPHA / CCRD IDs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Literal, Optional

from harness.canonical_case import (
    CanonicalCase,
    GoldLabel,
    HpoTerm,
    Language,
)

RareBenchSplit = Literal["RAMEDIS", "MME", "HMS", "LIRICAL", "PUMCH_ADM"]


def _parse_diseases(disease_list: list[str]) -> GoldLabel:
    omim, orpha, ccrd, name = None, None, None, None
    for d in disease_list or []:
        if d.startswith("OMIM:"):
            omim = omim or d
        elif d.startswith("ORPHA:"):
            orpha = orpha or d
        elif d.startswith("CCRD:"):
            ccrd = ccrd or d
        else:
            name = name or d
    return GoldLabel(
        omim_id=omim,
        orphanet_id=orpha,
        ccrd_id=ccrd,
        disease_name=name,
        hgnc_gene_id=None,
    )


def rarebench_record_to_canonical(
    record: dict, split: RareBenchSplit, case_idx: int
) -> CanonicalCase:
    gold = _parse_diseases(record.get("RareDisease", []))
    if not gold.has_any_id():
        raise ValueError(
            f"RareBench {split} record idx={case_idx} has no usable disease ID."
        )

    hpo_terms = [
        HpoTerm(id=h, label=None, onset=None, negated=False)
        for h in record.get("Phenotype", [])
        if isinstance(h, str) and h.startswith("HP:")
    ]

    language: Language = "zh" if split == "PUMCH_ADM" else "en"

    metadata = {}
    if record.get("Department"):
        metadata["department"] = record["Department"]

    return CanonicalCase(
        case_id=f"rarebench_{split}_{case_idx:05d}",
        source_dataset="rarebench",
        source_split=split,
        language=language,
        free_text_vignette=None,           # RareBench is structured HPO only
        synthetic_vignette=None,
        gold_hpo_terms=hpo_terms,
        variants=[],
        family=None,
        gold_label=gold,
        metadata=metadata,
    )


def ingest_rarebench(
    jsonl_path: Path | str,
    split: RareBenchSplit,
    limit: Optional[int] = None,
) -> Iterator[CanonicalCase]:
    """Yield CanonicalCase from a RareBench split JSONL.

    Convention: jsonl_path points to e.g. data/rarebench_hf/data_unzipped/data/RAMEDIS.jsonl
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
                yield rarebench_record_to_canonical(record, split=split, case_idx=lineno - 1)
                count += 1
                if limit and count >= limit:
                    return
            except Exception as e:
                print(
                    f"[ingest_rarebench] SKIP {path}:{lineno}: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr,
                )


__all__ = ["rarebench_record_to_canonical", "ingest_rarebench", "RareBenchSplit"]

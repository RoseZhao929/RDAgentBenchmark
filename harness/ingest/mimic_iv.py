"""Ingest adapter: MIMIC-IV hospitalizations -> CanonicalCase (Stream C).

Build a rare-disease slice from MIMIC-IV by:
1. Loading `diagnoses_icd.csv.gz` + `d_icd_diagnoses.csv.gz` to get all
   (hadm_id, icd_code, icd_version, long_title) rows
2. Cross-referencing ICD codes against Orphadata to identify rare disease
   admissions
3. Joining `admissions.csv.gz` + `patients.csv.gz` for demographics
4. Producing canonical_case JSONL

v1 limitation: no MIMIC-IV-Note (`discharge.csv.gz`) so we cannot do NLP recall
on the free-text narratives — only structured ICD-based identification. NLP
recall path is left as v2 future work.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterator, Optional
from xml.etree import ElementTree as ET

import pandas as pd

from harness.canonical_case import (
    CanonicalCase,
    Demographics,
    GoldLabel,
)

DEFAULT_MIMIC_ROOT = "data/mimic-iv-3.1"
DEFAULT_ORPHA_XML = "data/orphadata/en_product1.xml"


def build_icd_to_orpha_map(
    orpha_xml: str | Path = DEFAULT_ORPHA_XML,
) -> dict[str, list[tuple[str, str, str]]]:
    """Parse Orphadata cross-refs → {icd_code_no_dot: [(orpha_id, orpha_name, rel_type)]}.

    rel_type ∈ {"E" (exact), "NTBT" (narrower term broader term), "BTNT", "ND" (not declared)}
    """
    root = ET.parse(orpha_xml).getroot()
    mapping: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    for disorder in root.iter("Disorder"):
        orpha_code = disorder.findtext("OrphaCode")
        if not orpha_code:
            continue
        orpha_id = f"ORPHA:{orpha_code}"
        name_el = disorder.find("Name[@lang='en']")
        orpha_name = name_el.text.strip() if name_el is not None and name_el.text else ""

        for ext in disorder.findall(".//ExternalReference"):
            src = ext.findtext("Source")
            ref = ext.findtext("Reference")
            if src != "ICD-10" or not ref:
                continue
            mapping_type_el = ext.find(".//DisorderMappingRelation/Name[@lang='en']")
            rel = mapping_type_el.text.strip().split()[0] if mapping_type_el is not None else "ND"

            # Normalize ICD-10 code: strip dot
            icd_no_dot = ref.replace(".", "").upper()
            mapping[icd_no_dot].append((orpha_id, orpha_name, rel))

    return dict(mapping)


def build_rare_disease_slice(
    mimic_root: str | Path = DEFAULT_MIMIC_ROOT,
    orpha_xml: str | Path = DEFAULT_ORPHA_XML,
    relation_filter: tuple[str, ...] = ("E", "NTBT", "BTNT"),
    limit: Optional[int] = None,
) -> Iterator[CanonicalCase]:
    """Yield CanonicalCase for every MIMIC admission with ≥1 rare-disease ICD code.

    `relation_filter`:
      - "E" (Exact match) is conservative — single high-confidence Orphanet ID
      - "NTBT" / "BTNT" add candidates where the ICD code is broader/narrower
        than the Orphanet term. Use the full set for max recall; "E" only for precision.
    """
    mimic_root = Path(mimic_root)

    print("[mimic_iv] Parsing Orphadata ICD-10 cross-refs...", flush=True)
    icd_to_orpha = build_icd_to_orpha_map(orpha_xml)
    print(f"  ICD-10 codes with Orphanet mapping: {len(icd_to_orpha):,}", flush=True)

    print("[mimic_iv] Loading MIMIC diagnoses_icd.csv.gz...", flush=True)
    dx_path = mimic_root / "hosp" / "diagnoses_icd.csv.gz"
    diag = pd.read_csv(dx_path, dtype={"icd_code": str, "icd_version": int})
    print(f"  Total diagnosis rows: {len(diag):,}", flush=True)

    print("[mimic_iv] Loading d_icd_diagnoses.csv.gz for code → long_title...", flush=True)
    d_path = mimic_root / "hosp" / "d_icd_diagnoses.csv.gz"
    d_icd = pd.read_csv(d_path, dtype={"icd_code": str, "icd_version": int})
    icd_title = dict(zip(d_icd["icd_code"], d_icd["long_title"]))
    print(f"  Distinct ICD codes documented: {len(icd_title):,}", flush=True)

    # only ICD-10 (icd_version=10) for Orphadata join
    diag10 = diag[diag["icd_version"] == 10].copy()
    diag10["icd_clean"] = diag10["icd_code"].str.replace(".", "", regex=False).str.upper()

    # filter to rare-disease ICDs
    diag10["orpha_hits"] = diag10["icd_clean"].map(
        lambda c: [t for t in icd_to_orpha.get(c, []) if t[2] in relation_filter]
    )
    rd_diag = diag10[diag10["orpha_hits"].apply(lambda L: len(L) > 0)]
    print(f"  Rare-disease rows (rel ∈ {relation_filter}): {len(rd_diag):,}", flush=True)

    # group by hadm_id → list of (orpha_id, name, rel, icd_code)
    rd_by_hadm: dict[int, list[dict]] = defaultdict(list)
    for _, row in rd_diag.iterrows():
        for orpha_id, orpha_name, rel in row["orpha_hits"]:
            rd_by_hadm[int(row["hadm_id"])].append({
                "orpha_id": orpha_id,
                "orpha_name": orpha_name,
                "rel_type": rel,
                "icd_code": row["icd_code"],
                "icd_title": icd_title.get(row["icd_code"], ""),
            })
    print(f"  Unique rare-disease admissions: {len(rd_by_hadm):,}", flush=True)

    print("[mimic_iv] Loading admissions + patients...", flush=True)
    adm = pd.read_csv(
        mimic_root / "hosp" / "admissions.csv.gz",
        usecols=["subject_id", "hadm_id", "admittime", "race", "language"],
        parse_dates=["admittime"],
    )
    adm_lookup = adm.set_index("hadm_id").to_dict("index")

    pat = pd.read_csv(
        mimic_root / "hosp" / "patients.csv.gz",
        usecols=["subject_id", "gender", "anchor_age", "anchor_year"],
    )
    pat_lookup = pat.set_index("subject_id").to_dict("index")

    print("[mimic_iv] Building canonical cases...", flush=True)
    count = 0
    for hadm_id, hits in rd_by_hadm.items():
        adm_row = adm_lookup.get(hadm_id)
        if adm_row is None:
            continue
        pat_row = pat_lookup.get(adm_row["subject_id"])

        # Prefer Exact match if present, else first NTBT/BTNT
        primary = next((h for h in hits if h["rel_type"] == "E"), hits[0])

        # Demographics: MIMIC `anchor_age` is age at first admission year — approximate
        age = None
        if pat_row:
            try:
                age = float(pat_row["anchor_age"])
            except (TypeError, ValueError):
                pass

        sex = None
        if pat_row and pat_row.get("gender"):
            g = pat_row["gender"].upper()
            sex = "male" if g == "M" else ("female" if g == "F" else None)

        gold = GoldLabel(
            orphanet_id=primary["orpha_id"],
            disease_name=primary["orpha_name"],
            ccrd_id=None,
            omim_id=None,
        )

        # Build a synthetic "vignette" from ICD titles since we lack discharge notes
        icd_titles_text = "; ".join(sorted({h["icd_title"] for h in hits if h["icd_title"]}))
        synthetic = (
            f"A {int(age) if age else '?'}-year-old "
            f"{'male' if sex == 'male' else 'female' if sex == 'female' else 'patient'} "
            f"presenting at hospital admission with ICD-10-documented conditions: "
            f"{icd_titles_text}."
        ).strip()

        # NaN-safe language detection (admissions.language can be NaN float)
        lang_raw = adm_row.get("language")
        lang_str = str(lang_raw).lower() if isinstance(lang_raw, str) else ""
        language = "en" if lang_str in ("english", "?", "") else "other"

        yield CanonicalCase(
            case_id=f"mimic_iv_{hadm_id}",
            source_dataset="mimic_iv_rd",
            source_split="hosp",
            language=language,
            demographics=Demographics(age_at_diagnosis_years=age, sex=sex),
            free_text_vignette=None,        # would come from discharge.csv.gz (v2)
            synthetic_vignette=synthetic,
            gold_hpo_terms=[],              # would come from notes parsing (v2)
            variants=[],
            family=None,
            gold_label=gold,
            metadata={
                "race": adm_row.get("race"),
                "admittime": str(adm_row.get("admittime")),
                "all_orpha_hits": hits,      # full match list incl. non-primary
                "primary_relation": primary["rel_type"],
                "v1_limitation": "ICD-only slice; no MIMIC-IV-Note for narrative or HPO recall",
            },
        )
        count += 1
        if limit and count >= limit:
            return


def write_canonical_jsonl(
    out_path: str | Path,
    mimic_root: str | Path = DEFAULT_MIMIC_ROOT,
    orpha_xml: str | Path = DEFAULT_ORPHA_XML,
    relation_filter: tuple[str, ...] = ("E", "NTBT", "BTNT"),
    limit: Optional[int] = None,
) -> dict[str, int]:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = {"written": 0, "exact": 0, "ntbt": 0, "btnt": 0}
    with out.open("w") as f:
        for case in build_rare_disease_slice(
            mimic_root, orpha_xml, relation_filter=relation_filter, limit=limit
        ):
            f.write(case.model_dump_json() + "\n")
            stats["written"] += 1
            rel = case.metadata.get("primary_relation", "")
            if rel == "E":
                stats["exact"] += 1
            elif rel == "NTBT":
                stats["ntbt"] += 1
            elif rel == "BTNT":
                stats["btnt"] += 1
    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="data/mimic_iv_rd_slice/cases.jsonl",
    )
    parser.add_argument(
        "--mimic-root",
        default=DEFAULT_MIMIC_ROOT,
        help="MIMIC-IV root containing hosp/ (default: %(default)s)",
    )
    parser.add_argument(
        "--orpha-xml",
        default=DEFAULT_ORPHA_XML,
        help="Orphadata product 1 ICD-10 cross-reference XML (default: %(default)s)",
    )
    parser.add_argument(
        "--relations",
        default="E,NTBT,BTNT",
        help="Comma-separated relation types: E (exact), NTBT, BTNT",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rels = tuple(s.strip() for s in args.relations.split(","))
    print(f"Building MIMIC-IV rare-disease slice with relation filter: {rels}")
    stats = write_canonical_jsonl(
        args.out,
        mimic_root=args.mimic_root,
        orpha_xml=args.orpha_xml,
        relation_filter=rels,
        limit=args.limit,
    )
    print(f"DONE: {stats}")
    print(f"Output: {args.out}")

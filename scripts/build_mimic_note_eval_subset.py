"""Freeze the high-alignment, de-leaked MIMIC-IV note evaluation subset.

A hospitalization is "evaluable" only if ALL four hold:

  1. relation == "E"  — exact ICD-10 <-> Orphanet mapping (unambiguous gold).
  2. gold Orphanet id is a *rare* disorder — excludes Orphanet non-rare (flag
     32 / "NON RARE" name) and obsolete/deprecated/historical/inactive
     entities (flags 16/256/512/1024/8192).
  3. one of the gold-bearing ICD codes is the admission's PRINCIPAL diagnosis
     (diagnoses_icd.seq_num == 1) — the rare disease is the reason for THIS
     admission, not a prior/secondary code. This aligns the target with the
     early-window presentation the model actually reads.
  4. a discharge summary exists for the admission — otherwise no note input.

The model input is the de-leaked presentation span (see
``build_mimic_note_deleaked``): note text truncated before the first
diagnosis-revealing section, with any verbatim gold-name occurrence masked.
Gold lives in ``evaluation_only`` and never in ``model_input``.

Outputs stay under gitignored ``data/`` (credentialed). Only the printed
aggregate manifest (counts, hashes, per-disease histogram) is safe to copy.

No LLM calls. No fabrication. Deterministic.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# local import of the de-leaking primitives
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_mimic_note_deleaked import mask_gold, presentation_span  # noqa: E402

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

# Orphanet DisorderFlag values that disqualify an entity from being a usable
# rare-disease gold label.
BAD_FLAGS = {"32", "16", "256", "512", "1024", "8192"}


def build_excluded_orpha(xml_path: Path) -> set[str]:
    root = ET.parse(xml_path).getroot()
    excluded: set[str] = set()
    for d in root.iter("Disorder"):
        code = d.findtext("OrphaCode")
        if not code:
            continue
        oid = f"ORPHA:{code}"
        nm = d.find("Name[@lang='en']")
        name = nm.text if nm is not None and nm.text else ""
        flags = {fl.findtext("Value") for fl in d.findall(".//DisorderFlag")}
        if (flags & BAD_FLAGS) or name.upper().startswith("NON RARE"):
            excluded.add(oid)
    return excluded


def load_cohort(path: Path) -> dict[int, dict[str, Any]]:
    cohort: dict[int, dict[str, Any]] = {}
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            c = json.loads(line)
            hadm = int(c["case_id"].split("_")[-1])
            g = c.get("gold_label", {}) or {}
            hits = c.get("metadata", {}).get("all_orpha_hits") or []
            gcodes = {
                str(h.get("icd_code"))
                for h in hits
                if h.get("orpha_id") == g.get("orphanet_id")
            }
            demo = c.get("demographics", {}) or {}
            cohort[hadm] = {
                "rel": c.get("metadata", {}).get("primary_relation"),
                "gold_orpha": g.get("orphanet_id"),
                "gold_name": g.get("disease_name") or "",
                "gold_codes": gcodes,
                "age": demo.get("age_at_diagnosis_years"),
                "sex": demo.get("sex"),
            }
    return cohort


def load_principal(diag_path: Path) -> dict[int, set[str]]:
    principal: dict[int, set[str]] = defaultdict(set)
    with gzip.open(diag_path, "rt") as f:
        for row in csv.DictReader(f):
            if (
                row.get("seq_num") == "1"
                and row.get("icd_version") == "10"
                and row.get("hadm_id")
            ):
                principal[int(row["hadm_id"])].add(row["icd_code"])
    return principal


def load_notes(note_path: Path) -> dict[int, dict[str, str]]:
    """hadm_id -> {note_id, text} (first discharge summary per admission)."""
    notes: dict[int, dict[str, str]] = {}
    with gzip.open(note_path, "rt") as f:
        for row in csv.DictReader(f):
            h = row.get("hadm_id")
            if not h:
                continue
            hadm = int(h)
            if hadm not in notes:  # keep first DS
                notes[hadm] = {"note_id": row.get("note_id"), "text": row["text"]}
    return notes


def build(
    cohort_path: Path,
    diag_path: Path,
    note_path: Path,
    xml_path: Path,
    cap: int | None,
    out_path: Path | None,
) -> dict[str, Any]:
    excluded = build_excluded_orpha(xml_path)
    cohort = load_cohort(cohort_path)
    principal = load_principal(diag_path)
    notes = load_notes(note_path)

    # apply the four gates
    evaluable: list[int] = []
    for hadm, m in cohort.items():
        if m["rel"] != "E":
            continue
        if m["gold_orpha"] in excluded:
            continue
        if not (m["gold_codes"] & principal.get(hadm, set())):
            continue
        if hadm not in notes:
            continue
        evaluable.append(hadm)

    # optional per-disease balancing cap
    per_disease = Counter()
    kept: list[int] = []
    # stable order: by hadm_id so the cap is deterministic
    for hadm in sorted(evaluable):
        oid = cohort[hadm]["gold_orpha"]
        if cap is not None and per_disease[oid] >= cap:
            continue
        per_disease[oid] += 1
        kept.append(hadm)

    # write de-leaked records
    digest = hashlib.sha256()
    leak_after_trunc = 0
    masked_total = 0
    writer = out_path.open("w") if out_path else None
    try:
        for hadm in kept:
            m = cohort[hadm]
            pres = presentation_span(notes[hadm]["text"])
            masked, n_hits = mask_gold(pres, m["gold_name"])
            if n_hits:
                leak_after_trunc += 1
                masked_total += n_hits
            rec = {
                "case_id": f"mimic_iv_note_{hadm}",
                "hadm_id": hadm,
                "note_id": notes[hadm]["note_id"],
                "model_input": masked,
                "input_char_len": len(masked),
                "evaluation_only": {
                    "gold_orpha": m["gold_orpha"],
                    "gold_disease": m["gold_name"],
                    "relation": "E",
                    "gold_is_principal": True,
                },
                "demographics": {"age": m["age"], "sex": m["sex"]},
                "gold_name_verbatim_hits_before_mask": n_hits,
                "task_version": "mimic-note-eval-subset-v1",
            }
            line = json.dumps(rec, ensure_ascii=False)
            digest.update(line.encode("utf-8"))
            if writer:
                writer.write(line + "\n")
    finally:
        if writer:
            writer.close()

    dz = Counter(cohort[h]["gold_orpha"] for h in kept)
    names = {cohort[h]["gold_orpha"]: cohort[h]["gold_name"] for h in kept}
    top = [
        {"orpha": o, "name": names[o], "n": n} for o, n in dz.most_common(15)
    ]
    return {
        "gates": [
            "relation==E",
            "rare (excl Orphanet non-rare/obsolete flags)",
            "gold code is admission principal (seq_num==1)",
            "discharge summary exists",
        ],
        "excluded_orpha_ids": len(excluded),
        "n_evaluable_before_cap": len(evaluable),
        "per_disease_cap": cap,
        "n_final": len(kept),
        "n_distinct_diseases": len(dz),
        "leakage_self_check": {
            "gold_name_after_truncation_cases": leak_after_trunc,
            "masked_occurrences_total": masked_total,
            "residual_gold_in_model_input": 0,
        },
        "top_diseases": top,
        "output": str(out_path) if out_path else None,
        "output_sha256": digest.hexdigest(),
        "task_version": "mimic-note-eval-subset-v1",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cohort", type=Path,
                   default=Path("data/mimic_iv_rd_slice/cases_all_relations.jsonl"))
    p.add_argument("--diagnoses", type=Path,
                   default=Path("data/mimic-iv-3.1/hosp/diagnoses_icd.csv.gz"))
    p.add_argument("--notes", type=Path,
                   default=Path("data/mimic-iv-note-deidentified-free-text-clinical-notes-2.2/note/discharge.csv.gz"))
    p.add_argument("--orpha-xml", type=Path,
                   default=Path("data/orphadata/en_product1.xml"))
    p.add_argument("--cap", type=int, default=None,
                   help="Optional max cases per disease (balancing).")
    p.add_argument("--output", type=Path,
                   help="Credentialed JSONL output (keep under gitignored data/).")
    args = p.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(
        build(args.cohort, args.diagnoses, args.notes, args.orpha_xml,
              args.cap, args.output),
        indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

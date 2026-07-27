"""Build a de-leaked, note-based MIMIC-IV rare-disease diagnosis task (v2).

Motivation
----------
The v1 MIMIC slice fed ICD long titles into the model, so the gold Orphanet
name was printed verbatim in the input (data leakage). With MIMIC-IV-Note now
available, we can use the *presentation* portion of the discharge summary —
what is documented near admission (chief complaint, HPI, exam, family history)
— as the model input, and hold out the diagnosis-revealing sections.

De-leaking is two-stage and conservative:

1. **Section truncation.** Keep the note only up to (not including) the first
   diagnosis-revealing header (Brief Hospital Course, Discharge Diagnosis,
   Primary/Secondary Diagnosis, Impression, Assessment/Plan, Discharge
   Condition, Discharge Medications, ...). These sections encode the resolved
   diagnosis and are not available at prediction time.
2. **Verbatim gold masking.** Any case-insensitive occurrence of the gold
   Orphanet disease name (or its whitespace-normalized form) remaining in the
   kept text is replaced with ``[MASKED_DIAGNOSIS]``.

The gold label lives in ``evaluation_only`` and is never in ``model_input``.

Outputs stay under gitignored ``data/`` (credentialed MIMIC-derived text).
Only the printed aggregate manifest (counts, hashes, leakage self-check) is
safe to copy into an audit report. Review the PhysioNet DUA before sharing any
generated JSONL.

No LLM calls. No fabrication. Deterministic.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

# Headers that reveal the resolved diagnosis or are post-admission summaries.
# The note is cut at the FIRST occurrence of any of these (case-insensitive,
# anchored at line start, allowing leading whitespace).
CUT_HEADERS = [
    "Brief Hospital Course",
    "Discharge Diagnosis",
    "Discharge Diagnoses",
    "PRIMARY DIAGNOSIS",
    "SECONDARY DIAGNOSIS",
    "Primary Diagnosis",
    "Secondary Diagnosis",
    "Final Diagnosis",
    "Discharge Condition",
    "Discharge Medications",
    "Discharge Disposition",
    "Discharge Instructions",
    "Assessment and Plan",
    "Assessment/Plan",
    "IMPRESSION",
    "Impression",
    "Recommendations",
    "TRANSITIONAL ISSUES",
    "Followup Instructions",
]

_CUT_RE = re.compile(
    r"(?im)^[ \t]*(?:" + "|".join(re.escape(h) for h in CUT_HEADERS) + r")\s*:",
)

# csv module refuses very large clinical-note fields at the default limit.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def presentation_span(text: str) -> str:
    """Return the note prefix before the first diagnosis-revealing header."""
    m = _CUT_RE.search(text)
    return text[: m.start()] if m else text


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def mask_gold(text: str, gold_name: str) -> tuple[str, int]:
    """Replace verbatim gold-name occurrences; return (masked_text, n_hits)."""
    name = _norm_ws(gold_name)
    if not name:
        return text, 0
    # Case-insensitive, whitespace-flexible match of the full disease name.
    pat = re.compile(re.escape(name).replace(r"\ ", r"\s+"), re.IGNORECASE)
    n = len(pat.findall(text))
    if n:
        text = pat.sub("[MASKED_DIAGNOSIS]", text)
    return text, n


def load_cohort(path: Path) -> dict[int, dict[str, Any]]:
    """hadm_id -> {gold_orpha, gold_name, primary_relation, age, sex}."""
    cohort: dict[int, dict[str, Any]] = {}
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            c = json.loads(line)
            hadm = int(c["case_id"].split("_")[-1])
            g = c.get("gold_label", {}) or {}
            demo = c.get("demographics", {}) or {}
            cohort[hadm] = {
                "gold_orpha": g.get("orphanet_id"),
                "gold_name": g.get("disease_name") or "",
                "primary_relation": c.get("metadata", {}).get("primary_relation"),
                "age": demo.get("age_at_diagnosis_years"),
                "sex": demo.get("sex"),
            }
    return cohort


def iter_notes(path: Path) -> Iterable[dict[str, str]]:
    with gzip.open(path, "rt") as f:
        yield from csv.DictReader(f)


def load_case_id_filter(path: Path) -> set[str]:
    """Read a JSONL of eval records; return the set of their case_ids.

    Used by --leaked-416 to restrict the leaked variant to EXACTLY the same
    case_ids as the frozen de-leaked probe, so before/after is a true paired
    (same-case) comparison rather than two different cohorts.
    """
    ids: set[str] = set()
    with path.open() as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line)["case_id"])
    return ids


def build(
    cohort_path: Path,
    note_path: Path,
    out_path: Path | None,
    leaked: bool = False,
    restrict_case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Build the note-based task JSONL.

    leaked=False (default): de-leaked — truncate at first diagnosis-revealing
      header + verbatim-mask the gold name. This is the probe the paper uses.
    leaked=True: the BEFORE baseline — keep the FULL note (no truncation, no
      masking), so the diagnosis-revealing sections and the gold name stay in
      model_input. Quantifies how much of the score was answer-copying. Only
      meaningful when restrict_case_ids pins it to the de-leaked probe's cases.
    """
    cohort = load_cohort(cohort_path)
    counts = Counter()
    rel_counts = Counter()
    leak_after_truncation = 0       # cases where gold name survived the cut
    total_masked_occurrences = 0
    empty_after_truncation = 0
    presentation_lengths: list[int] = []
    writer = out_path.open("w") if out_path else None
    digest = hashlib.sha256()
    task_version = "mimic-note-leaked-v1" if leaked else "mimic-note-deleaked-v1"
    try:
        for row in iter_notes(note_path):
            h = row.get("hadm_id")
            if not h:
                continue
            hadm = int(h)
            meta = cohort.get(hadm)
            if meta is None:
                continue
            if restrict_case_ids is not None and f"mimic_iv_note_{hadm}" not in restrict_case_ids:
                continue
            counts["matched_notes"] += 1
            rel_counts[str(meta["primary_relation"])] += 1

            if leaked:
                # BEFORE: full note, no truncation, no masking. Report how many
                # times the gold name appears verbatim (leakage magnitude).
                model_input = row["text"]
                _pat = re.compile(
                    re.escape(_norm_ws(meta["gold_name"])).replace(r"\ ", r"\s+"),
                    re.IGNORECASE,
                ) if _norm_ws(meta["gold_name"]) else None
                n_hits = len(_pat.findall(model_input)) if _pat else 0
                if n_hits:
                    leak_after_truncation += 1
                    total_masked_occurrences += n_hits
            else:
                pres = presentation_span(row["text"])
                model_input, n_hits = mask_gold(pres, meta["gold_name"])
                if n_hits:
                    leak_after_truncation += 1
                    total_masked_occurrences += n_hits
            if not _norm_ws(model_input):
                empty_after_truncation += 1
            presentation_lengths.append(len(model_input))

            rec = {
                "case_id": f"mimic_iv_note_{hadm}",
                "hadm_id": hadm,
                "note_id": row.get("note_id"),
                "model_input": model_input,
                "input_char_len": len(model_input),
                "evaluation_only": {
                    "gold_orpha": meta["gold_orpha"],
                    "gold_disease": meta["gold_name"],
                    "primary_relation": meta["primary_relation"],
                },
                "demographics": {"age": meta["age"], "sex": meta["sex"]},
                "gold_name_verbatim_hits_before_mask": n_hits,
                "task_version": task_version,
            }
            line = json.dumps(rec, ensure_ascii=False)
            digest.update(line.encode("utf-8"))
            if writer:
                writer.write(line + "\n")
    finally:
        if writer:
            writer.close()

    lengths = sorted(presentation_lengths)
    n = len(lengths)
    median_len = lengths[n // 2] if n else 0
    return {
        "cohort_admissions": len(cohort),
        "matched_notes": counts["matched_notes"],
        "matched_by_relation": dict(sorted(rel_counts.items())),
        "leaked_variant": leaked,
        "leakage_self_check": {
            # For leaked=True these are gold-name hits in the FULL note (leakage
            # magnitude, NOT masked). For leaked=False they are survivors after
            # truncation, all masked → residual = 0.
            "cases_with_gold_name": leak_after_truncation,
            "pct_cases_with_gold_name": round(
                100 * leak_after_truncation / counts["matched_notes"], 2
            )
            if counts["matched_notes"]
            else 0.0,
            "total_gold_name_occurrences": total_masked_occurrences,
            "residual_gold_in_model_input": (
                total_masked_occurrences if leaked else 0
            ),
            "empty_input": empty_after_truncation,
        },
        "median_input_char_len": median_len,
        "output": str(out_path) if out_path else None,
        "output_sha256": digest.hexdigest(),
        "task_version": task_version,
        "cut_headers": [] if leaked else CUT_HEADERS,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--cohort",
        type=Path,
        default=Path("data/mimic_iv_rd_slice/cases_all_relations.jsonl"),
    )
    p.add_argument(
        "--notes",
        type=Path,
        default=Path(
            "data/mimic-iv-note-deidentified-free-text-clinical-notes-2.2/"
            "note/discharge.csv.gz"
        ),
    )
    p.add_argument(
        "--output",
        type=Path,
        help="Credentialed JSONL output (keep under gitignored data/).",
    )
    p.add_argument(
        "--leaked",
        action="store_true",
        help="Build the BEFORE baseline: full note, NO truncation, NO masking "
        "(gold name + diagnosis sections stay in model_input).",
    )
    p.add_argument(
        "--restrict-to",
        type=Path,
        help="JSONL of eval records; restrict output to EXACTLY these case_ids "
        "(e.g. the frozen 416 de-leaked probe) for a paired before/after set.",
    )
    args = p.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    restrict = load_case_id_filter(args.restrict_to) if args.restrict_to else None
    print(json.dumps(
        build(args.cohort, args.notes, args.output,
              leaked=args.leaked, restrict_case_ids=restrict),
        indent=2,
    ))


if __name__ == "__main__":
    main()

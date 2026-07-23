"""Build 24 h / 48 h MIMIC-IV structured-EHR snapshots.

Inputs are credentialed MIMIC-IV core tables. Outputs must remain under the
gitignored data tree. Diagnosis tables are used only to define the already
frozen cohort/gold and are never serialized into model input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_cohort(path: Path) -> tuple[dict[int, dict], dict[int, datetime]]:
    cases: dict[int, dict] = {}
    with path.open() as f:
        for line in f:
            case = json.loads(line)
            hadm = int(case["case_id"].removeprefix("mimic_iv_"))
            cases[hadm] = case
    return cases, {}


def load_admissions(root: Path, hadms: set[int]) -> dict[int, dict]:
    cols = ["subject_id", "hadm_id", "admittime", "admission_type", "admission_location"]
    df = pd.read_csv(root / "hosp/admissions.csv.gz", usecols=cols, parse_dates=["admittime"])
    df = df[df.hadm_id.isin(hadms)]
    return {int(r.hadm_id): r._asdict() for r in df.itertuples(index=False)}


def lab_labels(root: Path) -> dict[int, str]:
    df = pd.read_csv(root / "hosp/d_labitems.csv.gz", usecols=["itemid", "label", "fluid"])
    return {
        int(r.itemid): f"{r.label} ({r.fluid})"
        for r in df.itertuples(index=False)
    }


def add_labs(root: Path, hadms: set[int], admissions: dict[int, dict],
             events: dict[int, dict[int, dict]]) -> None:
    labels = lab_labels(root)
    use = [
        "hadm_id", "itemid", "charttime", "valuenum", "valueuom",
        "ref_range_lower", "ref_range_upper", "flag",
    ]
    for chunk in pd.read_csv(
        root / "hosp/labevents.csv.gz", usecols=use, parse_dates=["charttime"],
        date_format="%Y-%m-%d %H:%M:%S", chunksize=750_000,
    ):
        chunk = chunk[chunk.hadm_id.isin(hadms)]
        for r in chunk.itertuples(index=False):
            hadm = int(r.hadm_id)
            hours = (r.charttime.to_pydatetime() - admissions[hadm]["admittime"].to_pydatetime()).total_seconds() / 3600
            if hours < 0 or hours > 48:
                continue
            flag = str(r.flag).lower() if pd.notna(r.flag) else ""
            if flag not in {"abnormal", "high", "low"}:
                if pd.notna(r.valuenum) and pd.notna(r.ref_range_lower) and r.valuenum < r.ref_range_lower:
                    flag = "low"
                elif pd.notna(r.valuenum) and pd.notna(r.ref_range_upper) and r.valuenum > r.ref_range_upper:
                    flag = "high"
                else:
                    continue
            item = {
                "test": labels.get(int(r.itemid), f"LAB:{int(r.itemid)}"),
                "flag": flag,
                "value": float(r.valuenum) if pd.notna(r.valuenum) else None,
                "unit": str(r.valueuom) if pd.notna(r.valueuom) else None,
            }
            for window in (24, 48):
                if hours <= window:
                    events[hadm][window]["labs"].append(item)


def add_medications(root: Path, hadms: set[int], admissions: dict[int, dict],
                    events: dict[int, dict[int, dict]]) -> None:
    use = ["hadm_id", "starttime", "drug", "route"]
    for chunk in pd.read_csv(
        root / "hosp/prescriptions.csv.gz", usecols=use, parse_dates=["starttime"],
        date_format="%Y-%m-%d %H:%M:%S", chunksize=500_000,
    ):
        chunk = chunk[chunk.hadm_id.isin(hadms)]
        for r in chunk.itertuples(index=False):
            hadm = int(r.hadm_id)
            if pd.isna(r.starttime):
                continue
            hours = (r.starttime.to_pydatetime() - admissions[hadm]["admittime"].to_pydatetime()).total_seconds() / 3600
            if hours < 0 or hours > 48 or pd.isna(r.drug):
                continue
            item = {"drug": str(r.drug), "route": str(r.route) if pd.notna(r.route) else None}
            for window in (24, 48):
                if hours <= window:
                    events[hadm][window]["medications"].append(item)


def add_services(root: Path, hadms: set[int], admissions: dict[int, dict],
                 events: dict[int, dict[int, dict]]) -> None:
    use = ["hadm_id", "transfertime", "curr_service"]
    df = pd.read_csv(root / "hosp/services.csv.gz", usecols=use, parse_dates=["transfertime"])
    df = df[df.hadm_id.isin(hadms)]
    for r in df.itertuples(index=False):
        hadm = int(r.hadm_id)
        hours = (r.transfertime.to_pydatetime() - admissions[hadm]["admittime"].to_pydatetime()).total_seconds() / 3600
        if hours < 0 or hours > 48:
            continue
        for window in (24, 48):
            if hours <= window:
                events[hadm][window]["services"].append(str(r.curr_service))


def add_procedures(root: Path, hadms: set[int], admissions: dict[int, dict],
                   events: dict[int, dict[int, dict]]) -> None:
    dictionary = pd.read_csv(
        root / "hosp/d_icd_procedures.csv.gz",
        usecols=["icd_code", "icd_version", "long_title"],
        dtype={"icd_code": str},
    )
    labels = {
        (str(r.icd_code), int(r.icd_version)): str(r.long_title)
        for r in dictionary.itertuples(index=False)
    }
    df = pd.read_csv(
        root / "hosp/procedures_icd.csv.gz",
        usecols=["hadm_id", "chartdate", "icd_code", "icd_version"],
        dtype={"icd_code": str},
        parse_dates=["chartdate"],
    )
    df = df[df.hadm_id.isin(hadms)]
    for r in df.itertuples(index=False):
        hadm = int(r.hadm_id)
        # chartdate has day precision. Compare calendar days conservatively:
        # day 0/1 enters 24 h; day 0/1/2 enters 48 h.
        day = (r.chartdate.date() - admissions[hadm]["admittime"].date()).days
        if day < 0 or day > 2:
            continue
        item = labels.get((str(r.icd_code), int(r.icd_version)), "procedure")
        if day <= 1:
            events[hadm][24]["procedures"].append(item)
        events[hadm][48]["procedures"].append(item)


def dedupe(items: list) -> list:
    seen = set()
    out = []
    for item in items:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def build(root: Path, cohort_path: Path, output: Path) -> dict:
    cases, _ = load_cohort(cohort_path)
    hadms = set(cases)
    admissions = load_admissions(root, hadms)
    missing = sorted(hadms - set(admissions))
    if missing:
        raise ValueError(f"{len(missing)} cohort admissions missing from admissions.csv.gz")
    events = {
        h: {
            24: {"labs": [], "medications": [], "procedures": [], "services": []},
            48: {"labs": [], "medications": [], "procedures": [], "services": []},
        }
        for h in hadms
    }
    add_labs(root, hadms, admissions, events)
    add_medications(root, hadms, admissions, events)
    add_procedures(root, hadms, admissions, events)
    add_services(root, hadms, admissions, events)

    output.parent.mkdir(parents=True, exist_ok=True)
    nonempty = {24: 0, 48: 0}
    lexical_leaks = {24: 0, 48: 0}
    patient_ids = set()
    with output.open("w") as f:
        for hadm in sorted(hadms):
            case = cases[hadm]
            adm = admissions[hadm]
            patient_ids.add(int(adm["subject_id"]))
            for window in (24, 48):
                snapshot = {k: dedupe(v) for k, v in events[hadm][window].items()}
                if any(snapshot.values()):
                    nonempty[window] += 1
                model_input = {
                    "demographics": case.get("demographics", {}),
                    "admission_type": adm.get("admission_type"),
                    "admission_location": adm.get("admission_location"),
                    "structured_events": snapshot,
                }
                gold_name = (case["gold_label"].get("disease_name") or "").strip().lower()
                if gold_name and gold_name in json.dumps(model_input).lower():
                    lexical_leaks[window] += 1
                row = {
                    "case_id": case["case_id"],
                    "subject_group": hashlib.sha256(
                        f"mimic-structured-v1:{int(adm['subject_id'])}".encode()
                    ).hexdigest()[:16],
                    "window_hours": window,
                    "model_input": model_input,
                    "evaluation_only": {"gold_label": case["gold_label"]},
                    "task_version": "mimic-early-structured-v1",
                    "exclusions": [
                        "diagnosis codes and titles",
                        "clinical notes",
                        "events after window",
                        "provider identifiers",
                        "raw dates",
                    ],
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "task_version": "mimic-early-structured-v1",
        "cohort_sha256": digest(cohort_path),
        "output_sha256": digest(output),
        "n_admissions": len(hadms),
        "n_patients": len(patient_ids),
        "rows": len(hadms) * 2,
        "nonempty_snapshots": nonempty,
        "exact_gold_name_occurrences_in_model_input": lexical_leaks,
        "output": str(output),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mimic-root", type=Path, default=Path("data/mimic-iv-3.1"))
    p.add_argument(
        "--cohort", type=Path,
        default=Path("data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl"),
    )
    p.add_argument(
        "--output", type=Path,
        default=Path("data/mimic_iv_rd_slice/early_structured_v1.jsonl"),
    )
    args = p.parse_args()
    print(json.dumps(build(args.mimic_root, args.cohort, args.output), indent=2))


if __name__ == "__main__":
    main()

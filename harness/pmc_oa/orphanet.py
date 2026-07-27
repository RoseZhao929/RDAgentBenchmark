"""Step 4: Map LLM-extracted diagnosis strings to Orphanet IDs.

Strategy:
1. Parse Orphadata `en_product1.xml` once → build lookup tables:
   - name → ORPHA ID  (exact normalized match)
   - synonym → ORPHA ID
   - ORPHA → OMIM cross-refs
2. For each incoming diagnosis string:
   a. Normalize (lowercase, strip punctuation, collapse whitespace)
   b. Exact lookup
   c. If miss, rapidfuzz fuzzy match against full name list (threshold 90)
   d. Record top candidate(s) + score + match type

Output: JSONL with {pmc_id, extracted_diagnosis, orpha_id, omim_id, score,
                     match_type, candidates_top3}
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

# Resolve the Orphadata product1 XML portably:
#   1. ORPHA_PRODUCT1_XML env var if set;
#   2. else <repo-root>/data/orphadata/en_product1.xml (repo root = 3 parents up
#      from this file: harness/pmc_oa/orphanet.py -> repo root).
# Was previously hard-coded to the original author's Mac Desktop path, which
# broke every agent's name->ORPHA mapping step on any other machine.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORPHA_XML = os.environ.get(
    "ORPHA_PRODUCT1_XML",
    str(_REPO_ROOT / "data" / "orphadata" / "en_product1.xml"),
)


def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def parse_orphadata(xml_path: str | Path = DEFAULT_ORPHA_XML) -> dict:
    """Parse en_product1.xml into lookup tables.

    Returns dict with keys:
    - 'name_to_orpha': {normalized_name: ORPHA:NNNN}
    - 'orpha_to_canonical_name': {ORPHA:NNNN: 'Canonical English Name'}
    - 'orpha_to_omim': {ORPHA:NNNN: [OMIM:NNNNNN, ...]}
    - 'all_names': list of (normalized_name, ORPHA:NNNN) for rapidfuzz iteration
    """
    root = ET.parse(xml_path).getroot()
    name_to_orpha: dict[str, str] = {}
    orpha_to_canonical: dict[str, str] = {}
    orpha_to_omim: dict[str, list[str]] = {}

    for disorder in root.iter("Disorder"):
        orpha_code = disorder.findtext("OrphaCode")
        if not orpha_code:
            continue
        orpha_id = f"ORPHA:{orpha_code}"

        name_el = disorder.find("Name[@lang='en']")
        if name_el is None or not name_el.text:
            continue
        canonical = name_el.text.strip()
        orpha_to_canonical[orpha_id] = canonical

        # canonical name
        name_to_orpha[_normalize(canonical)] = orpha_id
        # synonyms
        for syn in disorder.findall(".//Synonym[@lang='en']"):
            if syn.text:
                key = _normalize(syn.text)
                # don't override canonical, but record synonyms too
                name_to_orpha.setdefault(key, orpha_id)

        # OMIM cross-refs
        omims: list[str] = []
        for ext in disorder.findall(".//ExternalReference"):
            src = ext.findtext("Source")
            ref = ext.findtext("Reference")
            if src == "OMIM" and ref:
                omims.append(f"OMIM:{ref}")
        if omims:
            orpha_to_omim[orpha_id] = omims

    all_names = list(name_to_orpha.items())
    return {
        "name_to_orpha": name_to_orpha,
        "orpha_to_canonical_name": orpha_to_canonical,
        "orpha_to_omim": orpha_to_omim,
        "all_names": all_names,
    }


def map_diagnosis(
    diagnosis: str,
    tables: dict,
    fuzzy_threshold: int = 90,
    return_top_k: int = 3,
) -> dict:
    """Map a single diagnosis string to Orphanet ID (+ OMIM if cross-referenced).

    Returns dict:
    - 'orpha_id': str or None
    - 'omim_ids': list of str (possibly empty)
    - 'matched_name': str (canonical name of matched ORPHA)
    - 'score': float (100 = exact, 0-99 = fuzzy)
    - 'match_type': 'exact_name' / 'exact_synonym' / 'fuzzy' / 'none'
    - 'top_candidates': [{'orpha_id', 'name', 'score'}, ...] for the top K
    """
    if not diagnosis or not isinstance(diagnosis, str):
        return {"orpha_id": None, "omim_ids": [], "matched_name": None,
                "score": 0.0, "match_type": "none", "top_candidates": []}

    normalized = _normalize(diagnosis)
    name_to_orpha = tables["name_to_orpha"]

    # exact
    if normalized in name_to_orpha:
        orpha = name_to_orpha[normalized]
        return {
            "orpha_id": orpha,
            "omim_ids": tables["orpha_to_omim"].get(orpha, []),
            "matched_name": tables["orpha_to_canonical_name"].get(orpha),
            "score": 100.0,
            "match_type": "exact_name",
            "top_candidates": [
                {"orpha_id": orpha, "name": tables["orpha_to_canonical_name"].get(orpha),
                 "score": 100.0}
            ],
        }

    # fuzzy
    if not HAS_RAPIDFUZZ:
        return {"orpha_id": None, "omim_ids": [], "matched_name": None,
                "score": 0.0, "match_type": "none",
                "top_candidates": [],
                "_note": "rapidfuzz not installed, skipped fuzzy match"}

    candidates_dict = tables["name_to_orpha"]
    # extract returns (string, score, key) when scorer chooses; use names as choices
    results = process.extract(
        normalized,
        candidates_dict.keys(),
        scorer=fuzz.WRatio,
        limit=return_top_k,
    )
    top_candidates = [
        {
            "orpha_id": candidates_dict[name],
            "name": tables["orpha_to_canonical_name"].get(candidates_dict[name], name),
            "score": float(score),
        }
        for name, score, _ in results
    ]

    if results and results[0][1] >= fuzzy_threshold:
        best_name, best_score, _ = results[0]
        best_orpha = candidates_dict[best_name]
        return {
            "orpha_id": best_orpha,
            "omim_ids": tables["orpha_to_omim"].get(best_orpha, []),
            "matched_name": tables["orpha_to_canonical_name"].get(best_orpha),
            "score": float(best_score),
            "match_type": "fuzzy",
            "top_candidates": top_candidates,
        }

    return {
        "orpha_id": None,
        "omim_ids": [],
        "matched_name": None,
        "score": float(results[0][1]) if results else 0.0,
        "match_type": "none",
        "top_candidates": top_candidates,
    }


def batch_map_extracted(
    extracted_jsonl: Path | str,
    out_path: Path | str,
    orpha_xml: str | Path = DEFAULT_ORPHA_XML,
) -> dict[str, int]:
    """Map every diagnosis in an LLM-extracted JSONL to ORPHA + OMIM.

    Returns stats: {"mapped": N, "unmapped": N, "no_diagnosis": N, "errors": N}.
    """
    tables = parse_orphadata(orpha_xml)
    print(f"  [orphanet] parsed {len(tables['name_to_orpha'])} name aliases, "
          f"{len(tables['orpha_to_canonical_name'])} disorders", flush=True)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {"mapped": 0, "unmapped": 0, "no_diagnosis": 0, "errors": 0}

    with Path(extracted_jsonl).open() as f_in, out_path.open("w") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                stats["errors"] += 1
                continue

            if rec.get("_error"):
                stats["errors"] += 1
                continue

            diagnosis = rec.get("final_diagnosis")
            if not diagnosis or rec.get("diagnosis_certainty") != "definitive":
                stats["no_diagnosis"] += 1
                continue

            mapped = map_diagnosis(diagnosis, tables)
            mapped["pmc_id"] = rec.get("pmc_id")
            mapped["extracted_diagnosis"] = diagnosis
            mapped["pub_year_in_text"] = rec.get("pub_year_in_text")
            f_out.write(json.dumps(mapped, ensure_ascii=False) + "\n")
            if mapped["orpha_id"]:
                stats["mapped"] += 1
            else:
                stats["unmapped"] += 1

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--extracted",
        default="/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/04_extracted.jsonl",
    )
    parser.add_argument(
        "--out",
        default="/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/05_orphanet_mapped.jsonl",
    )
    args = parser.parse_args()

    stats = batch_map_extracted(args.extracted, args.out)
    print(f"DONE: {stats}")

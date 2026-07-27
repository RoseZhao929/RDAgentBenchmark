"""Freeze the HPO-annotated line of the de-leaked MIMIC-note strict-A probe.

Why this line exists
--------------------
The other benchmark datasets (RareBench / PhenoPacket-Store / LIRICAL / RAMEDIS)
feed the model a per-CASE HPO phenotype list, so every case is 100% mappable to
an organ system (the H7 / H4 axes). MIMIC discharge notes are free text with NO
case-level HPO, so the closest structurally-comparable line keeps only cases
whose GOLD disease carries a DISEASE-level HPO annotation in Orphadata
en_product4.xml. Cases whose gold disease has no en_product4 annotation cannot
be placed on an organ system and are dropped here.

IMPORTANT (declare in the paper): the 271 dropped cases are dropped for
ANNOTATION ABSENCE, not for quality. Orphanet simply has no phenotype record for
those 37 gold diseases. This is a coverage limit of Orphadata, not a signal that
those cases are worse probes. And the HPO linkage here is DISEASE-level (gold
disease's Orphanet phenotype list), NOT case-level like the other datasets.

Result on the current uncapped strict-A set (687 / 105 diseases):
    -> HPO-annotated line = 416 cases / 68 diseases.

Deterministic. No LLM calls. No fabrication. Output under gitignored data/.
Reuses existing prediction receipts (416 subset of the already-scored 687).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


def load_hpo_annotated(product4: Path) -> set[str]:
    """Return the set of ORPHA ids that carry at least one HPO annotation."""
    root = ET.parse(product4).getroot()
    annotated: set[str] = set()
    for d in root.iter("Disorder"):
        code = d.findtext("OrphaCode")
        if not code:
            continue
        if any(h.text for h in d.findall(".//HPO/HPOId")):
            annotated.add(f"ORPHA:{code}")
    return annotated


def build(subset: Path, product4: Path, out_path: Path | None) -> dict[str, Any]:
    annotated = load_hpo_annotated(product4)
    rows = [json.loads(l) for l in subset.open() if l.strip()]

    kept: list[dict] = []
    dropped_orpha: Counter = Counter()
    for r in rows:
        oid = r["evaluation_only"]["gold_orpha"]
        if oid in annotated:
            kept.append(r)
        else:
            dropped_orpha[oid] += 1

    digest = hashlib.sha256()
    writer = out_path.open("w") if out_path else None
    try:
        for r in kept:
            line = json.dumps(r, ensure_ascii=False)
            digest.update(line.encode("utf-8"))
            if writer:
                writer.write(line + "\n")
    finally:
        if writer:
            writer.close()

    return {
        "input_n": len(rows),
        "input_diseases": len({r["evaluation_only"]["gold_orpha"] for r in rows}),
        "hpo_line_kept": len(kept),
        "hpo_line_diseases": len({r["evaluation_only"]["gold_orpha"] for r in kept}),
        "dropped_no_hpo_annotation_cases": len(rows) - len(kept),
        "dropped_no_hpo_annotation_diseases": len(dropped_orpha),
        "note": (
            "dropped = gold disease has NO en_product4 HPO annotation "
            "(coverage limit, NOT a quality filter). HPO linkage is "
            "disease-level, not case-level."
        ),
        "output": str(out_path) if out_path else None,
        "output_sha256": digest.hexdigest(),
        "task_version": "mimic-note-hpo-line-v1",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--subset", type=Path,
                   default=Path("data/mimic_iv_rd_slice/note_eval_strict_A_uncapped.jsonl"))
    p.add_argument("--product4", type=Path,
                   default=Path("data/orphadata/en_product4.xml"))
    p.add_argument("--output", type=Path,
                   help="Credentialed JSONL of the HPO-annotated line (gitignored data/).")
    args = p.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(args.subset, args.product4, args.output),
                      indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

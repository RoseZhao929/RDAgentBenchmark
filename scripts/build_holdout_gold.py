"""Build the post-cutoff PMC-OA holdout gold set, using the Opus-4.8 agent
annotation as a stand-in physician gold (to be swapped for the true physician
annotation at camera-ready; §9 L5 / A5).

For each of the 198 held-out cases:
  - gold_label = the Orphanet/OMIM of the verified final diagnosis (Opus flagged
    0/198 diagnoses wrong, so we keep the extractor's Orphanet mapping).
  - phenotype input = extracted HPO terms MINUS the terms Opus flagged as wrong
    (the "physician-cleaned" phenotype list), rendered as a free-text vignette.

Output: data/pmc_oa_holdout/holdout_gold_opus.jsonl  (CanonicalCase JSON per line)
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.canonical_case import CanonicalCase, GoldLabel, Demographics

import os
POOL = ROOT / os.environ.get("HG_POOL", "data/pmc_oa_holdout/HANDOFF_v3/candidates_full_pool.jsonl")
ANN = ROOT / os.environ.get("HG_ANN", "data/pmc_oa_holdout/opus48_annotation.jsonl")
OUT = ROOT / os.environ.get("HG_OUT", "data/pmc_oa_holdout/holdout_gold_opus.jsonl")


def main():
    pool = {str(json.loads(l)["pmc_id"]): json.loads(l) for l in open(POOL)}
    ann = {json.loads(l)["pmc_id"]: json.loads(l) for l in open(ANN)}
    out = OUT.open("w")
    n = 0
    for pid, a in ann.items():
        p = pool.get(pid)
        if not p or not p.get("orpha_id"):
            continue
        # physician(=Opus)-cleaned phenotype list
        wrong = set(x.lower().strip() for x in a.get("opus_wrong_hpo_terms", []))
        hpo = [h for h in p.get("hpo_phenotypes", []) if h.lower().strip() not in wrong]
        if not hpo:
            hpo = p.get("hpo_phenotypes", [])  # fall back if Opus rejected all
        vignette = "Clinical phenotypes: " + "; ".join(hpo) + "."
        sex = p.get("sex") if p.get("sex") in ("male", "female", "unknown") else None
        demo = Demographics(
            age_at_onset_years=p.get("age_at_presentation_years"),
            sex=sex,
        )
        omim = None
        oms = p.get("omim_ids") or []
        if oms and str(oms[0]).startswith("OMIM:"):
            omim = str(oms[0])
        gold = GoldLabel(
            orphanet_id=p["orpha_id"],
            omim_id=omim,
            disease_name=p.get("matched_orpha_name") or p.get("extracted_diagnosis"),
        )
        case = CanonicalCase(
            case_id=f"pmc_{pid}",
            source_dataset="pmc_oa_holdout",
            source_split="opus_gold_v1",
            gold_label=gold,
            demographics=demo,
            free_text_vignette=vignette,
            language="en",
        )
        out.write(case.model_dump_json() + "\n")
        n += 1
    out.close()
    print(f"[holdout-gold] wrote {n} cases -> {OUT}")


if __name__ == "__main__":
    main()

"""Prevalence-stratification analysis for the de-leaked MIMIC-note probe.

Answers three questions raised in review:

  1. What is the prevalence-class distribution of the uncapped strict-A subset
     (687), and how does it compare to the full rare-disease cohort (150,033)?
  2. Is the uncapped subset within +/-2pp of the full cohort per class (i.e. is
     it already a valid prevalence-stratified sample, so no reweighting needed)?
  3. Re-score DeepSeek / Opus on the uncapped strict-A set under BOTH micro
     (per-case) and macro (per-disease) averaging, reusing existing receipts.

Prevalence classes come from Orphadata en_product9_prev.xml (PrevalenceClass).
We collapse to the standard rarity bands used elsewhere in the benchmark.

HPO organ-system stratification is NOT computed: the repo only ships hp.obo
(the ontology tree), not an orpha->HPO annotation (en_product4_HPO.xml /
phenotype.hpoa). That half of the reviewer's method needs that file.

Deterministic. No LLM calls. No fabrication. Reuses gitignored data/ + receipts.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Collapse Orphanet PrevalenceClass strings into ordered rarity bands.
BAND = {
    ">1 / 1000": "common(>1/1k)",
    "1-5 / 10 000": "moderate(1-5/10k)",
    "6-9 / 10 000": "moderate(1-5/10k)",
    "1-9 / 100 000": "rare(1-9/100k)",
    "1-9 / 1 000 000": "ultra(1-9/1M)",
    "<1 / 1 000 000": "super-rare(<1/1M)",
    "Unknown": "unknown",
    "Not yet documented": "unknown",
}
BAND_ORDER = ["common(>1/1k)", "moderate(1-5/10k)", "rare(1-9/100k)",
              "ultra(1-9/1M)", "super-rare(<1/1M)", "unknown"]


def load_prev_class(xml_path: Path) -> dict[str, str]:
    """ORPHA -> rarity band. Prefer a documented 'Point prevalence' class;
    fall back to any available class; else 'unknown'."""
    root = ET.parse(xml_path).getroot()
    out: dict[str, str] = {}
    for d in root.iter("Disorder"):
        code = d.findtext("OrphaCode")
        if not code:
            continue
        oid = f"ORPHA:{code}"
        chosen = None
        fallback = None
        for prev in d.findall(".//Prevalence"):
            ptype = prev.findtext("PrevalenceType/Name") or ""
            pc = prev.find("PrevalenceClass/Name")
            if pc is None or not pc.text:
                continue
            fallback = pc.text
            if ptype == "Point prevalence":
                chosen = pc.text
        cls = chosen or fallback
        if cls:
            out[oid] = BAND.get(cls, "unknown")
    return out


def dist(orphas: list[str], prev: dict[str, str]) -> dict[str, float]:
    c = Counter(prev.get(o, "unknown") for o in orphas)
    n = sum(c.values())
    return {b: round(100 * c.get(b, 0) / n, 1) for b in BAND_ORDER} if n else {}


def rescore(preds_path: Path, keep_ids: set[str],
            case_disease: dict[str, str]) -> dict[str, Any]:
    """micro R@1/R@5 and macro (per-disease) R@1/R@5 over keep_ids."""
    n = h1 = h5 = 0
    per_dz_hit: dict[str, list[int]] = defaultdict(list)
    per_dz_hit5: dict[str, list[int]] = defaultdict(list)
    for line in preds_path.open():
        if not line.strip():
            continue
        p = json.loads(line)
        cid = p["case_id"]
        if cid not in keep_ids:
            continue
        n += 1
        a = 1 if p.get("_hit1") else 0
        b = 1 if p.get("_hit5") else 0
        h1 += a
        h5 += b
        dz = case_disease[cid]
        per_dz_hit[dz].append(a)
        per_dz_hit5[dz].append(b)
    macro1 = sum(sum(v) / len(v) for v in per_dz_hit.values()) / len(per_dz_hit) if per_dz_hit else 0
    macro5 = sum(sum(v) / len(v) for v in per_dz_hit5.values()) / len(per_dz_hit5) if per_dz_hit5 else 0
    return {
        "n_cases": n,
        "n_diseases": len(per_dz_hit),
        "micro_R@1": round(h1 / n, 4) if n else None,
        "micro_R@5": round(h5 / n, 4) if n else None,
        "macro_R@1": round(macro1, 4),
        "macro_R@5": round(macro5, 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", type=Path,
                    default=Path("data/mimic_iv_rd_slice/cases_all_relations.jsonl"))
    ap.add_argument("--v2", type=Path,
                    default=Path("data/mimic_iv_rd_slice/note_eval_subset_v2.jsonl"))
    ap.add_argument("--strict-a-script-out", type=Path,
                    default=Path("data/mimic_iv_rd_slice/note_eval_strict_A_uncapped.jsonl"),
                    help="uncapped strict-A jsonl (build first with build_mimic_note_strict_A on v2)")
    ap.add_argument("--prev-xml", type=Path,
                    default=Path("data/orphadata/en_product9_prev.xml"))
    ap.add_argument("--deepseek", type=Path,
                    default=Path("data/mimic_iv_rd_slice/predictions_mimic_note_deepseek_v4.jsonl"))
    ap.add_argument("--opus", type=Path,
                    default=Path("data/mimic_iv_rd_slice/predictions_mimic_note_opus48.jsonl"))
    args = ap.parse_args()

    prev = load_prev_class(args.prev_xml)

    # full cohort orphas (E-only, to match the evaluable line's gold universe)
    cohort_orphas: list[str] = []
    for line in args.cohort.open():
        if not line.strip():
            continue
        c = json.loads(line)
        if c.get("metadata", {}).get("primary_relation") != "E":
            continue
        g = c.get("gold_label", {}) or {}
        if g.get("orphanet_id"):
            cohort_orphas.append(g["orphanet_id"])

    # uncapped strict-A subset
    sa_rows = [json.loads(l) for l in args.strict_a_script_out.open() if l.strip()]
    sa_ids = {r["case_id"] for r in sa_rows}
    sa_orphas = [r["evaluation_only"]["gold_orpha"] for r in sa_rows]
    case_disease = {r["case_id"]: r["evaluation_only"]["gold_orpha"] for r in sa_rows}

    d_full = dist(cohort_orphas, prev)
    d_sa = dist(sa_orphas, prev)
    delta = {b: round(d_sa.get(b, 0) - d_full.get(b, 0), 1) for b in BAND_ORDER}
    within_2pp = {b: abs(delta[b]) <= 2.0 for b in BAND_ORDER}

    out = {
        "Q1_prevalence_distribution": {
            "full_cohort_E_only_n": len(cohort_orphas),
            "uncapped_strictA_n": len(sa_orphas),
            "full_cohort_pct": d_full,
            "uncapped_strictA_pct": d_sa,
        },
        "Q2_within_2pp_check": {
            "delta_pp (subset - full)": delta,
            "within_2pp_per_band": within_2pp,
            "all_bands_within_2pp": all(within_2pp.values()),
            "verdict": (
                "uncapped strict-A already tracks the full cohort within 2pp on "
                "every band -> usable as-is with micro averaging"
                if all(within_2pp.values())
                else "some bands exceed 2pp -> micro is biased; report macro-avg "
                "or reweight by band"
            ),
        },
        "Q3_rescore_uncapped_strictA": {
            "DeepSeek_V4": rescore(args.deepseek, sa_ids, case_disease),
            "Opus_4.8": rescore(args.opus, sa_ids, case_disease),
        },
        "HPO_organ_system_note": (
            "NOT computed: repo ships only hp.obo (ontology tree), not an "
            "orpha->HPO annotation (en_product4_HPO.xml / phenotype.hpoa). "
            "The reviewer's HPO-organ-system stratification needs that file."
        ),
        "prevalence_coverage": (
            f"{sum(1 for o in set(sa_orphas) if o in prev)}/"
            f"{len(set(sa_orphas))} distinct strict-A diseases have a prevalence class"
        ),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""HPO organ-system + rarity stratification for the MIMIC-note strict-A probe.

Uses the SAME organ-system scheme as the rest of the benchmark
(scripts/ablation_H4_H7_specialty.py): the top-level children of
HP:0000118 ("Phenotypic abnormality") in data/hpo/hp.obo — the ~23 broad
"organ system" categories. This keeps the MIMIC probe comparable to the H7
specialty axis used for RareBench / PhenoPacket-Store.

MIMIC cases have no case-level HPO (free-text notes). We attach phenotypes at
the DISEASE level via Orphadata en_product4.xml (ORPHA -> HPO term list), then
map each HPO term to its top-level organ system(s):

  * H7-style specialty  = the modal (most frequent) organ system across the
    gold disease's HPO terms.
  * H4-style complexity = number of distinct organ systems the disease touches
    (single=1 / oligo=2-3 / multi=4+).

Diseases without an en_product4 HPO annotation are reported separately as
"no_hpo_annotation" and NOT force-fit into a system (honest coverage limit:
~35% of our gold diseases lack an annotation).

Rarity band comes from en_product9_prev.xml (same as analyze_*_prevalence.py).

Scores reuse existing receipts (no new LLM calls). Reports micro + macro R@1
overall and per organ-system / per rarity band. Deterministic, no fabrication.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = "HP:0000118"


def load_hpo_roots(obo: Path):
    """Return (systems_fn, root_name). Mirrors ablation_H4_H7_specialty.py."""
    terms: dict[str, dict] = {}
    cur = None
    for line in obo.open():
        line = line.rstrip("\n")
        if line == "[Term]":
            cur = {"parents": set(), "id": None, "name": None}
        elif cur is not None and line.startswith("id: HP:"):
            cur["id"] = line[4:].strip()
        elif cur is not None and line.startswith("name:"):
            cur["name"] = line[6:].strip()
        elif cur is not None and line.startswith("is_a:"):
            m = re.match(r"is_a:\s*(HP:\d+)", line)
            if m:
                cur["parents"].add(m.group(1))
        elif line == "" and cur is not None and cur.get("id"):
            terms[cur["id"]] = cur
            cur = None
    roots = {t for t, d in terms.items() if ROOT in d["parents"]}
    name = {t: terms[t]["name"] for t in roots}
    cache: dict[str, set] = {}

    def systems(hp: str) -> set:
        if hp in cache:
            return cache[hp]
        seen: set = set()
        stack = [hp]
        found: set = set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            if x in roots:
                found.add(x)
            for p in terms.get(x, {}).get("parents", ()):
                stack.append(p)
        cache[hp] = found
        return found

    return systems, name


def short(label: str) -> str:
    return re.sub(r"^Abnormality of (the )?", "", label or "").strip() or label


def load_orpha_hpo(xml: Path) -> dict[str, list[str]]:
    root = ET.parse(xml).getroot()
    out: dict[str, list[str]] = {}
    for d in root.iter("Disorder"):
        code = d.findtext("OrphaCode")
        if not code:
            continue
        hpos = [h.text for h in d.findall(".//HPO/HPOId") if h.text]
        if hpos:
            out[f"ORPHA:{code}"] = hpos
    return out


def load_rarity(prev_xml: Path) -> dict[str, str]:
    BAND = {
        ">1 / 1000": "common", "1-5 / 10 000": "moderate", "6-9 / 10 000": "moderate",
        "1-9 / 100 000": "rare", "1-9 / 1 000 000": "ultra",
        "<1 / 1 000 000": "super-rare", "Unknown": "unknown", "Not yet documented": "unknown",
    }
    root = ET.parse(prev_xml).getroot()
    out: dict[str, str] = {}
    for d in root.iter("Disorder"):
        code = d.findtext("OrphaCode")
        if not code:
            continue
        chosen = fb = None
        for pv in d.findall(".//Prevalence"):
            t = pv.findtext("PrevalenceType/Name") or ""
            pc = pv.find("PrevalenceClass/Name")
            if pc is None or not pc.text:
                continue
            fb = pc.text
            if t == "Point prevalence":
                chosen = pc.text
        cls = chosen or fb
        if cls:
            out[f"ORPHA:{code}"] = BAND.get(cls, "unknown")
    return out


def disease_system(orpha: str, orpha_hpo: dict, systems_fn, root_name: dict):
    """Return (modal_system_label or None, n_distinct_systems)."""
    hpos = orpha_hpo.get(orpha)
    if not hpos:
        return None, 0
    sysc: Counter = Counter()
    for hp in hpos:
        for s in systems_fn(hp):
            sysc[s] += 1
    if not sysc:
        return None, 0
    modal = max(sysc.items(), key=lambda kv: kv[1])[0]
    return short(root_name.get(modal, modal)), len(sysc)


def rescore(preds: Path, keep_ids: set, key_of: dict, group_of: dict) -> dict:
    """micro/macro R@1 grouped by group_of[case_id]. key_of = case->disease."""
    grp = defaultdict(lambda: {"n": 0, "h1": 0, "h5": 0, "dz": defaultdict(list)})
    tot = {"n": 0, "h1": 0, "h5": 0, "dz": defaultdict(list)}
    for line in preds.open():
        if not line.strip():
            continue
        p = json.loads(line)
        c = p["case_id"]
        if c not in keep_ids:
            continue
        a = 1 if p.get("_hit1") else 0
        b = 1 if p.get("_hit5") else 0
        dz = key_of[c]
        g = group_of.get(c, "no_hpo_annotation")
        for bucket in (grp[g], tot):
            bucket["n"] += 1
            bucket["h1"] += a
            bucket["h5"] += b
            bucket["dz"][dz].append(a)

    def fmt(bkt):
        n = bkt["n"]
        macro = sum(sum(v) / len(v) for v in bkt["dz"].values()) / len(bkt["dz"]) if bkt["dz"] else 0
        return {
            "n": n, "n_dz": len(bkt["dz"]),
            "micro_R@1": round(bkt["h1"] / n, 4) if n else None,
            "macro_R@1": round(macro, 4),
        }

    return {"overall": fmt(tot),
            "by_group": {g: fmt(b) for g, b in sorted(grp.items(), key=lambda kv: -kv[1]["n"])}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", type=Path,
                    default=Path("data/mimic_iv_rd_slice/note_eval_strict_A_uncapped.jsonl"))
    ap.add_argument("--obo", type=Path, default=Path("data/hpo/hp.obo"))
    ap.add_argument("--product4", type=Path, default=Path("data/orphadata/en_product4.xml"))
    ap.add_argument("--prev", type=Path, default=Path("data/orphadata/en_product9_prev.xml"))
    ap.add_argument("--preds", type=Path, nargs="+", required=True,
                    help="prediction receipt files (one per model)")
    args = ap.parse_args()

    systems_fn, root_name = load_hpo_roots(args.obo)
    orpha_hpo = load_orpha_hpo(args.product4)
    rarity = load_rarity(args.prev)

    rows = [json.loads(l) for l in args.subset.open() if l.strip()]
    ids = {r["case_id"] for r in rows}
    key_of = {r["case_id"]: r["evaluation_only"]["gold_orpha"] for r in rows}

    specialty_of: dict[str, str] = {}
    complexity_of: dict[str, str] = {}
    rarity_of: dict[str, str] = {}
    n_no_hpo = 0
    for r in rows:
        o = r["evaluation_only"]["gold_orpha"]
        spec, nsys = disease_system(o, orpha_hpo, systems_fn, root_name)
        if spec is None:
            n_no_hpo += 1
            specialty_of[r["case_id"]] = "no_hpo_annotation"
            complexity_of[r["case_id"]] = "no_hpo_annotation"
        else:
            specialty_of[r["case_id"]] = spec
            complexity_of[r["case_id"]] = ("single(1)" if nsys == 1 else
                                           "oligo(2-3)" if nsys <= 3 else "multi(4+)")
        rarity_of[r["case_id"]] = rarity.get(o, "not-in-prev-xml")

    out: dict[str, Any] = {
        "subset_n": len(rows),
        "distinct_diseases": len(set(key_of.values())),
        "cases_without_hpo_annotation": n_no_hpo,
        "organ_system_scheme": "top-level children of HP:0000118 (hp.obo), same as H7",
        "specialty_distribution": dict(Counter(specialty_of.values()).most_common()),
        "complexity_distribution": dict(Counter(complexity_of.values()).most_common()),
        "rarity_distribution": dict(Counter(rarity_of.values()).most_common()),
        "models": {},
    }
    for pf in args.preds:
        model = pf.stem.replace("predictions_mimic_note_", "")
        out["models"][model] = {
            "by_specialty": rescore(pf, ids, key_of, specialty_of),
            "by_complexity": rescore(pf, ids, key_of, complexity_of),
            "by_rarity": rescore(pf, ids, key_of, rarity_of),
        }
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

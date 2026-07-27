#!/usr/bin/env python
"""Data-leakage audit for the four non-MIMIC RareAgentBench datasets.

READ-ONLY. No LLM calls. Pure string/ID matching.

For each dataset we reconstruct EXACTLY the case-specific model-input text that
the agent sees. The runner (scripts/phase4a_runner.py) calls
adapter.predict(..., eval_mode="gold_hpo"), and every free-text adapter routes
through harness.agents._adapter_utils.case_to_question(case, "gold_hpo").

Under eval_mode="gold_hpo" the branch priority in case_to_question is:
    demographics block, then:
      gold_hpo_terms  ->  synthetic_vignette  ->  free_text_vignette
(the `end_to_end` free-text branch is NEVER taken by the main matrix runner).

So the per-dataset input is:
  - phenopacket_store : HPO term labels + IDs   (gold_hpo_terms present)
  - rarebench         : HPO IDs (labels None)   (gold_hpo_terms present)
  - rarearena_rds     : free_text_vignette (case_report prose)  <- no HPO
  - pmc_oa / precutoff: free_text_vignette ("Clinical phenotypes: ...")  <- no HPO

We measure the leakage channels on the CASE-SPECIFIC input only (we exclude the
fixed Task-instruction boilerplate that case_to_question appends, because it is
constant and contains an example acronym 'CADASIL' that would otherwise create
spurious hits). This is the conservative choice and is stated in the summary.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path
from typing import Optional

ROOT = Path("/home/research/RDAgentBenchmark")
sys.path.insert(0, str(ROOT))

from harness.pmc_oa.orphanet import _normalize  # same normalizer the repo scores with
from harness.canonical_case import CanonicalCase
from harness.ingest import (
    ingest_phenopacket_store,
    ingest_rarebench,
    ingest_rarearena,
)
from harness.agents._adapter_utils import hpo_terms_to_text

from rapidfuzz import fuzz
from xml.etree import ElementTree as ET

ORPHA_XML = ROOT / "data/orphadata/en_product1.xml"
OUTDIR = ROOT / "audit_frozen/leakage_audit"
SEED = 42
RAREARENA_SAMPLE = 2000

SHORT_SYN_MAXLEN = 4   # synonyms with normalized len <= this are "short/acronym"
LONG_SYN_MINLEN = 5    # headline synonym channel uses len >= this
FUZZY_THRESHOLD = 90


# --------------------------------------------------------------------------
# Orphanet tables: canonical name + synonyms + OMIM<->ORPHA crossmap
# --------------------------------------------------------------------------
def build_orpha_tables():
    print("[audit] parsing en_product1.xml ...", flush=True)
    root = ET.parse(ORPHA_XML).getroot()
    orpha_to_canonical: dict[str, str] = {}
    orpha_to_synonyms: dict[str, list[str]] = {}   # normalized synonym strings (excl canonical)
    orpha_to_omim: dict[str, list[str]] = {}
    omim_to_orpha: dict[str, list[str]] = {}

    for disorder in root.iter("Disorder"):
        code = disorder.findtext("OrphaCode")
        if not code:
            continue
        orpha_id = f"ORPHA:{code}"
        name_el = disorder.find("Name[@lang='en']")
        if name_el is None or not name_el.text:
            continue
        orpha_to_canonical[orpha_id] = name_el.text.strip()

        syns: list[str] = []
        for syn in disorder.findall(".//Synonym[@lang='en']"):
            if syn.text:
                syns.append(_normalize(syn.text))
        orpha_to_synonyms[orpha_id] = syns

        omims: list[str] = []
        for ext in disorder.findall(".//ExternalReference"):
            if ext.findtext("Source") == "OMIM":
                ref = ext.findtext("Reference")
                if ref:
                    oid = f"OMIM:{ref}"
                    omims.append(oid)
                    omim_to_orpha.setdefault(oid, []).append(orpha_id)
        if omims:
            orpha_to_omim[orpha_id] = omims

    print(f"[audit]   {len(orpha_to_canonical)} disorders, "
          f"{len(omim_to_orpha)} OMIM->ORPHA keys", flush=True)
    return {
        "orpha_to_canonical": orpha_to_canonical,
        "orpha_to_synonyms": orpha_to_synonyms,
        "orpha_to_omim": orpha_to_omim,
        "omim_to_orpha": omim_to_orpha,
    }


# --------------------------------------------------------------------------
# Input reconstruction (case-specific part of case_to_question, gold_hpo mode)
# --------------------------------------------------------------------------
def build_input_text(case: CanonicalCase) -> str:
    parts: list[str] = []
    d = case.demographics
    if d and (d.age_at_onset_years is not None or d.sex or d.ancestry):
        bits = []
        if d.age_at_onset_years is not None:
            bits.append(f"age at onset {d.age_at_onset_years} y")
        if d.sex:
            bits.append(d.sex)
        if d.ancestry:
            bits.append(d.ancestry)
        if bits:
            parts.append("Demographics: " + ", ".join(bits) + ".")
    # eval_mode == "gold_hpo": end_to_end branch NOT taken
    if case.gold_hpo_terms:
        parts.append("Clinical phenotypes (HPO): "
                     + hpo_terms_to_text(case.gold_hpo_terms) + ".")
    elif case.synthetic_vignette:
        parts.append("Clinical vignette: " + case.synthetic_vignette.strip())
    elif case.free_text_vignette:
        parts.append("Clinical vignette: " + case.free_text_vignette.strip())
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# Identifier-format variants for the gold IDs
# --------------------------------------------------------------------------
def id_variants(orpha_id: Optional[str], omim_id: Optional[str]) -> list[str]:
    out: list[str] = []
    if orpha_id:
        num = orpha_id.split(":", 1)[1]
        out += [f"orpha:{num}", f"orpha {num}", f"orphanet:{num}",
                f"orphanet {num}", f"orpha{num}"]
        # bare number only if reasonably long to avoid trivial hits
        if len(num) >= 4:
            out.append(num)
    if omim_id:
        num = omim_id.split(":", 1)[1]
        out += [f"omim:{num}", f"omim {num}", f"mim:{num}", f"mim {num}",
                f"omim{num}", f"#{num}", num]
    return [_normalize(v) for v in out if v]


# --------------------------------------------------------------------------
# Per-case leakage evaluation
# --------------------------------------------------------------------------
def eval_case(case: CanonicalCase, tables: dict, has_title: bool):
    inp = build_input_text(case)
    norm_inp = _normalize(inp)
    # raw (non-normalized) input lowercased for identifier '#' style checks
    raw_low = inp.lower()

    gl = case.gold_label
    orpha = gl.orphanet_id
    omim = gl.omim_id
    name = gl.disease_name

    # resolve an ORPHA for synonym lookup (map OMIM->ORPHA if needed)
    syn_orphas: list[str] = []
    if orpha and orpha in tables["orpha_to_synonyms"]:
        syn_orphas = [orpha]
    elif omim and omim in tables["omim_to_orpha"]:
        syn_orphas = tables["omim_to_orpha"][omim]

    # channel 1: exact gold disease name (normalized substring)
    exact_name_hit = 0
    if name:
        nn = _normalize(name)
        if len(nn) >= 3 and nn in norm_inp:
            exact_name_hit = 1
    # also try canonical ORPHA name if different
    if not exact_name_hit and syn_orphas:
        for oid in syn_orphas:
            can = tables["orpha_to_canonical"].get(oid)
            if can:
                cn = _normalize(can)
                if len(cn) >= 3 and cn in norm_inp:
                    exact_name_hit = 1
                    break

    # channel 2: identifier in input
    identifier_hit = 0
    for v in id_variants(orpha, omim):
        if v and v in norm_inp:
            identifier_hit = 1
            break
    if not identifier_hit and omim:  # '#' style not preserved by _normalize
        num = omim.split(":", 1)[1]
        if f"#{num}" in raw_low or f"omim {num}" in raw_low:
            identifier_hit = 1

    # channel 3: synonym in input (long >=5 headline; short separate)
    synonym_hit = 0            # long synonyms (len>=5)
    synonym_short_hit = 0      # short/acronym synonyms
    synonym_na = 1 if not syn_orphas else 0
    if syn_orphas:
        for oid in syn_orphas:
            for s in tables["orpha_to_synonyms"].get(oid, []):
                if not s:
                    continue
                if s in norm_inp:
                    if len(s) >= LONG_SYN_MINLEN:
                        synonym_hit = 1
                    elif len(s) <= SHORT_SYN_MAXLEN:
                        synonym_short_hit = 1
            if synonym_hit:
                break

    # secondary fuzzy synonym signal (WRatio >= 90 of any long synonym vs input)
    fuzzy_syn_hit = 0
    if syn_orphas and not synonym_hit and norm_inp:
        for oid in syn_orphas:
            for s in tables["orpha_to_synonyms"].get(oid, []):
                if len(s) >= LONG_SYN_MINLEN and fuzz.partial_ratio(s, norm_inp) >= FUZZY_THRESHOLD:
                    fuzzy_syn_hit = 1
                    break
            if fuzzy_syn_hit:
                break

    # channel 4: title leakage — first sentence of free text (heuristic).
    # None of these 4 datasets carries a dedicated `title` field, so this is a
    # first-sentence heuristic on free-text datasets only; n/a for HPO datasets.
    title_hit = 0
    title_na = 0 if has_title else 1
    if has_title and case.free_text_vignette:
        first = case.free_text_vignette.split(".")[0]
        nt = _normalize(first)
        if name:
            nn = _normalize(name)
            if len(nn) >= 3 and nn in nt:
                title_hit = 1
        if not title_hit and syn_orphas:
            for oid in syn_orphas:
                can = tables["orpha_to_canonical"].get(oid)
                if can and len(_normalize(can)) >= 3 and _normalize(can) in nt:
                    title_hit = 1
                    break
                for s in tables["orpha_to_synonyms"].get(oid, []):
                    if len(s) >= LONG_SYN_MINLEN and s in nt:
                        title_hit = 1
                        break
                if title_hit:
                    break

    return {
        "input_char_len": len(inp),
        "exact_name_hit": exact_name_hit,
        "identifier_hit": identifier_hit,
        "synonym_hit": synonym_hit,
        "synonym_short_hit": synonym_short_hit,
        "synonym_na": synonym_na,
        "fuzzy_syn_hit": fuzzy_syn_hit,
        "title_hit": title_hit,
        "title_na": title_na,
    }


# --------------------------------------------------------------------------
# Dataset loaders -> list[CanonicalCase]
# --------------------------------------------------------------------------
def load_all():
    dsets = {}

    dsets["phenopacket_store"] = list(
        ingest_phenopacket_store(ROOT / "data/phenopacket_store/notebooks")
    )

    rb = []
    for split in ["RAMEDIS", "LIRICAL", "MME", "HMS"]:
        rb += list(ingest_rarebench(
            ROOT / f"data/rarebench_hf/data_unzipped/data/{split}.jsonl", split))
    dsets["rarebench"] = rb

    # RareArena: deterministic sample
    all_ra = list(ingest_rarearena(
        ROOT / "data/rarearena/benchmark_data/RDS_benchmark.jsonl", "RDS"))
    rng = random.Random(SEED)
    if len(all_ra) > RAREARENA_SAMPLE:
        ra = rng.sample(all_ra, RAREARENA_SAMPLE)
    else:
        ra = all_ra
    dsets["rarearena_rds"] = ra
    dsets["_rarearena_total"] = len(all_ra)

    for name, path in [
        ("pmc_oa_holdout", ROOT / "data/pmc_oa_holdout/holdout_gold_opus.jsonl"),
        ("pmc_precutoff", ROOT / "data/pmc_precutoff/holdout_gold_opus.jsonl"),
    ]:
        cases = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    cases.append(CanonicalCase.model_validate_json(line))
                except Exception as e:
                    print(f"[audit] skip {name}: {e}", file=sys.stderr)
        dsets[name] = cases

    return dsets


# has_title: which datasets carry free-text where a first-sentence title
# heuristic is meaningful. Only the free-text datasets. PMC vignettes are a
# "Clinical phenotypes: ..." list (no real title) -> mark n/a.
HAS_TITLE = {
    "phenopacket_store": False,
    "rarebench": False,
    "rarearena_rds": True,   # case_report prose, first sentence ~ presentation line
    "pmc_oa_holdout": False,
    "pmc_precutoff": False,
}


def main():
    tables = build_orpha_tables()
    dsets = load_all()
    ra_total = dsets.pop("_rarearena_total")

    csv_rows = []
    summary = {}

    order = ["phenopacket_store", "rarebench", "rarearena_rds",
             "pmc_oa_holdout", "pmc_precutoff"]

    for ds in order:
        cases = dsets[ds]
        has_title = HAS_TITLE[ds]
        n = len(cases)
        agg = dict(exact=0, ident=0, syn=0, syn_short=0, syn_na=0,
                   fuzzy=0, title=0, title_na=0)
        for c in cases:
            r = eval_case(c, tables, has_title)
            agg["exact"] += r["exact_name_hit"]
            agg["ident"] += r["identifier_hit"]
            agg["syn"] += r["synonym_hit"]
            agg["syn_short"] += r["synonym_short_hit"]
            agg["syn_na"] += r["synonym_na"]
            agg["fuzzy"] += r["fuzzy_syn_hit"]
            agg["title"] += r["title_hit"]
            agg["title_na"] += r["title_na"]
            split = c.source_split or ""
            csv_rows.append({
                "dataset": ds,
                "split": split,
                "case_id": c.case_id,
                "gold_orpha": c.gold_label.orphanet_id or "",
                "gold_omim": c.gold_label.omim_id or "",
                "gold_name": c.gold_label.disease_name or "",
                "input_char_len": r["input_char_len"],
                "exact_name_hit": r["exact_name_hit"],
                "identifier_hit": r["identifier_hit"],
                "synonym_hit": r["synonym_hit"],
                "title_hit": r["title_hit"],
            })
        # synonym denominator excludes n/a (no ORPHA) cases
        syn_denom = n - agg["syn_na"]
        summary[ds] = {
            "n": n,
            "exact_rate": agg["exact"] / n if n else 0.0,
            "syn_rate": (agg["syn"] / syn_denom) if syn_denom else None,
            "syn_denom": syn_denom,
            "syn_na": agg["syn_na"],
            "syn_short": agg["syn_short"],
            "fuzzy_rate": (agg["fuzzy"] / syn_denom) if syn_denom else None,
            "ident_rate": agg["ident"] / n if n else 0.0,
            "title_rate": (agg["title"] / n) if (n and not HAS_TITLE[ds] is False) else None,
            "title_na": agg["title_na"],
            "title_hits": agg["title"],
        }
        print(f"[audit] {ds}: n={n} exact={agg['exact']} ident={agg['ident']} "
              f"syn(long)={agg['syn']}/{syn_denom} syn_short={agg['syn_short']} "
              f"fuzzy={agg['fuzzy']} title={agg['title']} (na_syn={agg['syn_na']})",
              flush=True)

    # write CSV
    OUTDIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTDIR / "leakage_case_level.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "dataset", "split", "case_id", "gold_orpha", "gold_omim",
            "gold_name", "input_char_len", "exact_name_hit", "identifier_hit",
            "synonym_hit", "title_hit"])
        w.writeheader()
        w.writerows(csv_rows)
    print(f"[audit] wrote {csv_path} ({len(csv_rows)} rows)")

    # dump machine summary for the .md writer
    (OUTDIR / "_summary.json").write_text(json.dumps(
        {"summary": summary, "rarearena_total": ra_total,
         "rarearena_sample": RAREARENA_SAMPLE}, indent=2))
    print("[audit] wrote _summary.json")


if __name__ == "__main__":
    main()

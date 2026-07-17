"""Ingest adapter: GA4GH Phenopackets -> CanonicalCase.

Source: data/phenopacket_store/notebooks/<disease>/phenopackets/*.json

The Phenopacket schema is rich (variants with ACMG, structural type, etc.) but
this dataset has no free-text vignette and rarely has pedigree blocks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator, List, Optional

from harness.canonical_case import (
    AcmgClassification,
    CanonicalCase,
    Demographics,
    GoldLabel,
    HpoTerm,
    Sex,
    Variant,
    Zygosity,
)

# Regex for ISO 8601 duration like "P34Y" / "P3Y6M" / "P0Y2M14D"
_DURATION_PATTERN = re.compile(
    r"P(?:(?P<years>\d+(?:\.\d+)?)Y)?"
    r"(?:(?P<months>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<days>\d+(?:\.\d+)?)D)?"
)


def _parse_iso8601_to_years(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    m = _DURATION_PATTERN.fullmatch(iso)
    if not m:
        return None
    y = float(m.group("years") or 0)
    mo = float(m.group("months") or 0)
    d = float(m.group("days") or 0)
    return y + mo / 12.0 + d / 365.25


def _parse_sex(s: Optional[str]) -> Optional[Sex]:
    if not s:
        return None
    s = s.upper()
    if s == "MALE":
        return "male"
    if s == "FEMALE":
        return "female"
    return "unknown"


# Map ACMG strings to our enum
_ACMG_MAP: dict[str, AcmgClassification] = {
    "PATHOGENIC": "pathogenic",
    "LIKELY_PATHOGENIC": "likely_pathogenic",
    "UNCERTAIN_SIGNIFICANCE": "vus",
    "VARIANT_OF_UNCERTAIN_SIGNIFICANCE": "vus",
    "LIKELY_BENIGN": "likely_benign",
    "BENIGN": "benign",
    "NOT_PROVIDED": "unknown",
}

# Map GENO allelic state IDs to zygosity
# Reference: http://www.sequenceontology.org/browser/current_svn/term/SO:0001023
_GENO_ZYG_MAP: dict[str, Zygosity] = {
    "GENO:0000135": "het",            # heterozygous
    "GENO:0000136": "hom",            # homozygous
    "GENO:0000134": "hemi",           # hemizygous
    "GENO:0000402": "compound_het",   # compound heterozygous
}


def _parse_variant(genomic_interp: dict) -> Optional[Variant]:
    vi = genomic_interp.get("variantInterpretation", {})
    vd = vi.get("variationDescriptor", {})
    gene = vd.get("geneContext", {}) or {}
    structural = vd.get("structuralType", {}) or {}
    allelic = vd.get("allelicState", {}) or {}
    expressions = {e.get("syntax"): e.get("value") for e in vd.get("expressions", [])}

    return Variant(
        gene_symbol=gene.get("symbol"),
        hgnc_id=gene.get("valueId"),
        transcript=None,  # Could be parsed from hgvs.c if needed
        hgvs_c=expressions.get("hgvs.c"),
        hgvs_p=expressions.get("hgvs.p"),
        structural_type=structural.get("id"),
        acmg_classification=_ACMG_MAP.get(
            vi.get("acmgPathogenicityClassification", "").upper()
        ),
        zygosity=_GENO_ZYG_MAP.get(allelic.get("id", "")),
        de_novo=None,  # Phenopacket-Store rarely marks de novo explicitly
    )


def _parse_phenotypic_features(features: List[dict]) -> List[HpoTerm]:
    out: List[HpoTerm] = []
    for f in features:
        t = f.get("type", {})
        hp_id = t.get("id", "")
        if not hp_id.startswith("HP:"):
            continue
        onset = f.get("onset", {}).get("ontologyClass", {}).get("id")
        out.append(
            HpoTerm(
                id=hp_id,
                label=t.get("label"),
                onset=onset if onset and onset.startswith("HP:") else None,
                negated=bool(f.get("excluded", False)),
            )
        )
    return out


def _parse_gold_label(interpretations: List[dict]) -> Optional[GoldLabel]:
    for interp in interpretations:
        diag = interp.get("diagnosis", {})
        disease = diag.get("disease", {})
        disease_id = disease.get("id", "")
        if not disease_id:
            continue
        omim = disease_id if disease_id.startswith("OMIM:") else None
        orpha = disease_id if disease_id.startswith("ORPHA:") else None

        # primary causative gene if any
        gene_id = None
        for gi in diag.get("genomicInterpretations", []):
            vd = gi.get("variantInterpretation", {}).get("variationDescriptor", {})
            gene = vd.get("geneContext", {}) or {}
            if gene.get("valueId"):
                gene_id = gene["valueId"]
                break

        return GoldLabel(
            omim_id=omim,
            orphanet_id=orpha,
            ccrd_id=None,
            disease_name=disease.get("label"),
            hgnc_gene_id=gene_id,
        )
    return None


def phenopacket_to_canonical(pp: dict, source_split: Optional[str] = None) -> CanonicalCase:
    """Convert a single GA4GH Phenopacket dict to CanonicalCase.

    `source_split` if provided is the gene/disease folder name (e.g. 'ABCA4').
    """
    subject = pp.get("subject", {})
    age_iso = subject.get("timeAtLastEncounter", {}).get("age", {}).get("iso8601duration")

    variants: List[Variant] = []
    for interp in pp.get("interpretations", []):
        for gi in interp.get("diagnosis", {}).get("genomicInterpretations", []):
            v = _parse_variant(gi)
            if v:
                variants.append(v)

    gold = _parse_gold_label(pp.get("interpretations", []))
    if gold is None or not gold.has_any_id():
        raise ValueError(
            f"Phenopacket {pp.get('id', '?')} has no usable diagnosis ID; skip or fix source."
        )

    return CanonicalCase(
        case_id=pp.get("id", "UNKNOWN"),
        source_dataset="phenopacket_store",
        source_split=source_split,
        language="en",
        demographics=Demographics(
            age_at_onset_years=_parse_iso8601_to_years(age_iso),
            sex=_parse_sex(subject.get("sex")),
        ),
        free_text_vignette=None,            # Phenopackets have no native prose
        synthetic_vignette=None,             # to be filled later by harness.synth
        gold_hpo_terms=_parse_phenotypic_features(pp.get("phenotypicFeatures", [])),
        variants=variants,
        family=None,                          # rare in this dataset
        gold_label=gold,
        metadata={
            "raw_subject_id": subject.get("id"),
            "metaData": pp.get("metaData", {}),
        },
    )


def ingest_phenopacket_store(
    notebooks_dir: Path | str,
    limit: Optional[int] = None,
) -> Iterator[CanonicalCase]:
    """Yield CanonicalCase for every phenopacket JSON under notebooks/<disease>/phenopackets/.

    Skips records lacking a usable diagnosis (logs to stderr).
    """
    import sys

    root = Path(notebooks_dir)
    count = 0
    for disease_dir in sorted(root.iterdir()):
        if not disease_dir.is_dir():
            continue
        pp_dir = disease_dir / "phenopackets"
        if not pp_dir.is_dir():
            continue
        for json_file in sorted(pp_dir.glob("*.json")):
            try:
                pp = json.loads(json_file.read_text())
                case = phenopacket_to_canonical(pp, source_split=disease_dir.name)
                yield case
                count += 1
                if limit and count >= limit:
                    return
            except Exception as e:
                print(
                    f"[ingest_phenopacket_store] SKIP {json_file}: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )


__all__ = ["phenopacket_to_canonical", "ingest_phenopacket_store"]

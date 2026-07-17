"""Canonical case object — unified schema across all source datasets.

Every dataset (Phenopacket-Store, RareBench, RareArena, MIMIC-IV slice, PMC OA
holdout, MyGene2, DDD) ingests into this single representation, and every agent
adapter projects from this representation into the agent's native input.

Design principles:
- All fields except `case_id`, `source_dataset`, `gold_label` are Optional —
  different datasets have different coverage (see INGEST_REPORT.md in each
  data/*/ subdir).
- Disease identifiers carried as side-by-side OMIM / Orphanet / CCRD IDs since
  datasets disagree on which is primary. Evaluation logic must accept
  cross-mapped matches.
- HPO terms structured (not just IDs) to preserve onset / negation.
- Variants structured but NOT raw VCF — for agents needing raw VCF, point at
  `vcf_path` (local file, never transmitted to external APIs).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# -------- enums via Literal --------

Sex = Literal["male", "female", "unknown"]
Language = Literal["en", "zh", "other"]
SourceDataset = Literal[
    "phenopacket_store",
    "rarebench",       # all 5 splits use this; subset goes in source_split
    "rarearena",       # RDS / RDC in source_split
    "mimic_iv_rd",
    "pmc_oa_holdout",
    "mygene2",
    "ddd",
]
ModeOfInheritance = Literal["AD", "AR", "XLD", "XLR", "MT", "Y", "DI", "isolated", "other"]
AcmgClassification = Literal[
    "pathogenic", "likely_pathogenic", "vus", "likely_benign", "benign", "unknown"
]
Zygosity = Literal["het", "hom", "hemi", "compound_het", "mosaic", "unknown"]


# -------- nested models --------


class Demographics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_at_onset_years: Optional[float] = None
    age_at_diagnosis_years: Optional[float] = None
    sex: Optional[Sex] = None
    ancestry: Optional[str] = Field(
        default=None,
        description="Free-text ancestry as reported (e.g., 'European', 'East Asian'); "
        "ingest does NOT normalize across datasets — that's done at analysis time.",
    )


class HpoTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=r"^HP:\d{7}$", description="HPO ID, e.g., HP:0001250")
    label: Optional[str] = None
    onset: Optional[str] = Field(
        default=None,
        description="HPO onset modifier ID (e.g., HP:0003621 = Juvenile onset)",
    )
    negated: bool = False


class Variant(BaseModel):
    """Structured variant info for Pillar 3 (genotype-aware).

    Note: this is NOT a full VCF row — it's the structured fields typically
    available in a phenopacket's variationDescriptor or a clinical report.
    For agents requiring raw VCF, use vcf_path on the parent CanonicalCase.
    """

    model_config = ConfigDict(extra="forbid")

    gene_symbol: Optional[str] = Field(default=None, description="e.g., 'ABCA4'")
    hgnc_id: Optional[str] = Field(default=None, description="e.g., 'HGNC:34'")
    transcript: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    structural_type: Optional[str] = Field(
        default=None, description="Sequence Ontology ID, e.g., 'SO:1000029'"
    )
    acmg_classification: Optional[AcmgClassification] = None
    zygosity: Optional[Zygosity] = None
    de_novo: Optional[bool] = None


class FamilyHistory(BaseModel):
    """Pillar 4 (Family-aware) inputs.

    Most datasets DO NOT populate this. Phenopacket-Store has hints via
    subject.id (e.g., 'II.2') but rarely full pedigree. MyGene2 / DDD will
    populate this in v2.
    """

    model_config = ConfigDict(extra="forbid")

    trio_mode: bool = False
    pedigree_json: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GA4GH pedigree block or PED-style record; structure dataset-specific.",
    )
    moi_label: Optional[ModeOfInheritance] = None
    affected_relatives: List[str] = Field(
        default_factory=list,
        description="Free-text descriptions of affected relatives.",
    )


class GoldLabel(BaseModel):
    """Ground-truth diagnosis. At least one ID must be present.

    Datasets disagree:
    - Phenopacket-Store uses OMIM primarily
    - RareArena uses Orphanet primarily
    - RareBench provides multiple (OMIM + ORPHA + CCRD)
    - MIMIC slice uses Orphanet (post ICD→Orphanet mapping)
    - PUMCH-ADM and the Chinese layer prefer CCRD

    Evaluation must do cross-mapping via Orphadata `en_product1.xml`.
    """

    model_config = ConfigDict(extra="forbid")

    omim_id: Optional[str] = Field(default=None, pattern=r"^OMIM:\d{6}$")
    orphanet_id: Optional[str] = Field(default=None, pattern=r"^ORPHA:\d+$")
    ccrd_id: Optional[str] = Field(default=None, pattern=r"^CCRD:\d+(\.\d+)?$")
    disease_name: Optional[str] = None
    hgnc_gene_id: Optional[str] = Field(
        default=None,
        description="Primary causative gene; used for Pillar 3 Gene Top-k metric.",
    )

    def has_any_id(self) -> bool:
        return any([self.omim_id, self.orphanet_id, self.ccrd_id])


# -------- top-level case --------


class CanonicalCase(BaseModel):
    """Unified per-case representation used across all pillars and agents.

    Required: case_id, source_dataset, gold_label (with at least one ID).
    Everything else is Optional — adapter sets what the source provides.
    """

    model_config = ConfigDict(extra="forbid")

    # identity
    case_id: str = Field(..., description="Unique within source_dataset.")
    source_dataset: SourceDataset
    source_split: Optional[str] = Field(
        default=None,
        description="e.g., 'RAMEDIS', 'LIRICAL', 'RDS', 'RDC'",
    )

    # language layer (Bias eval lens)
    language: Language = "en"

    # demographics (Bias eval lens)
    demographics: Demographics = Field(default_factory=Demographics)

    # text inputs
    free_text_vignette: Optional[str] = Field(
        default=None, description="Natural-language case description as in source."
    )
    synthetic_vignette: Optional[str] = Field(
        default=None,
        description="LLM-synthesized vignette from HPO list when source lacks free text. "
        "Marked separately to distinguish from gold prose.",
    )

    # phenotype (Pillar 1 gold output / Pillar 2 input)
    gold_hpo_terms: List[HpoTerm] = Field(default_factory=list)

    # genotype (Pillar 3)
    variants: List[Variant] = Field(default_factory=list)
    vcf_path: Optional[str] = Field(
        default=None,
        description="Absolute local path to raw VCF. Never transmitted to cloud APIs.",
    )

    # family (Pillar 4)
    family: Optional[FamilyHistory] = None

    # ground truth
    gold_label: GoldLabel

    # arbitrary source-specific metadata (publication_date, department, raw fields, etc.)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# -------- exports --------

__all__ = [
    "CanonicalCase",
    "Demographics",
    "HpoTerm",
    "Variant",
    "FamilyHistory",
    "GoldLabel",
    "Sex",
    "Language",
    "SourceDataset",
    "ModeOfInheritance",
    "AcmgClassification",
    "Zygosity",
]

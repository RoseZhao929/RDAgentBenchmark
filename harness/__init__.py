"""Rare Disease Agent Benchmark — evaluation harness.

Public surface:
- `CanonicalCase` and friends from `harness.canonical_case` — unified case schema
- `harness.ingest.*` — per-dataset adapters producing CanonicalCase
- `harness.metrics.*` — Recall@k, MRR, Brier/ECE, P/R/F1, pass^k, etc.
- `harness.logging` — prediction log schema + cost/latency capture

Usage:
    from harness import CanonicalCase
    from harness.ingest import ingest_phenopacket_store
    cases = ingest_phenopacket_store("/path/to/data/phenopacket_store/notebooks")
"""

from harness.canonical_case import (
    AcmgClassification,
    CanonicalCase,
    Demographics,
    FamilyHistory,
    GoldLabel,
    HpoTerm,
    Language,
    ModeOfInheritance,
    Sex,
    SourceDataset,
    Variant,
    Zygosity,
)

__all__ = [
    "AcmgClassification",
    "CanonicalCase",
    "Demographics",
    "FamilyHistory",
    "GoldLabel",
    "HpoTerm",
    "Language",
    "ModeOfInheritance",
    "Sex",
    "SourceDataset",
    "Variant",
    "Zygosity",
]

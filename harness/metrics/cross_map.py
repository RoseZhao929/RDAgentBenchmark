"""OMIM ↔ Orphanet cross-mapping for evaluator (S1).

Wraps Orphadata cross-references so the metric layer can:
- check whether a predicted disease ID (any ontology) hits the gold disease ID
  (potentially in a different ontology)
- canonicalize IDs to a preferred ontology for reporting

Source: `data/orphadata/en_product1.xml` (Orphadata, CC-BY-4.0, 11,456 disorders,
4,978 with OMIM cross-refs as of 2025-12-09 snapshot).

Wraps `harness.pmc_oa.orphanet.parse_orphadata` rather than re-parsing.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from harness.canonical_case import GoldLabel


@lru_cache(maxsize=1)
def _load() -> dict:
    """Load Orphadata cross-mapping tables (cached once per process)."""
    from harness.pmc_oa.orphanet import parse_orphadata

    tables = parse_orphadata()

    # invert orpha_to_omim → omim_to_orpha (one OMIM may map to multiple ORPHAs)
    omim_to_orpha: dict[str, list[str]] = {}
    for orpha, omims in tables["orpha_to_omim"].items():
        for omim in omims:
            omim_to_orpha.setdefault(omim, []).append(orpha)

    return {
        "orpha_to_omim": tables["orpha_to_omim"],          # ORPHA -> [OMIM, ...]
        "omim_to_orpha": omim_to_orpha,                     # OMIM  -> [ORPHA, ...]
        "orpha_canonical": tables["orpha_to_canonical_name"],
    }


def omim_to_orpha(omim_id: str) -> List[str]:
    """Return list of ORPHA IDs that cross-reference this OMIM ID.

    Empty list if no mapping (Orphadata covers only the genetic/rare ones —
    expect ~50% coverage of OMIM-listed Mendelian disorders).
    """
    if not omim_id or not omim_id.startswith("OMIM:"):
        return []
    return _load()["omim_to_orpha"].get(omim_id, [])


def orpha_to_omim(orpha_id: str) -> List[str]:
    """Return list of OMIM IDs cross-referenced by this ORPHA ID.

    Many ORPHA codes are gene-disease level and may map to multiple OMIM IDs.
    """
    if not orpha_id or not orpha_id.startswith("ORPHA:"):
        return []
    return _load()["orpha_to_omim"].get(orpha_id, [])


def equivalent_ids(id1: str, id2: str) -> bool:
    """True iff id1 and id2 represent the same disease across ontologies.

    Handles:
    - identity match (same prefix, same code)
    - OMIM ↔ ORPHA via Orphadata cross-refs
    """
    if not id1 or not id2:
        return False
    if id1 == id2:
        return True

    p1, p2 = id1.split(":")[0], id2.split(":")[0]
    if p1 == "OMIM" and p2 == "ORPHA":
        return id2 in omim_to_orpha(id1)
    if p1 == "ORPHA" and p2 == "OMIM":
        return id2 in orpha_to_omim(id1)
    return False


def gold_hit_with_crossmap(predicted_id: str, gold: GoldLabel) -> bool:
    """Like `harness.metrics.accuracy.is_hit` but allows cross-ontology match.

    A prediction hits the gold if it equals ANY of:
    - gold's parallel OMIM / ORPHA / CCRD IDs
    - their cross-mapped equivalents via Orphadata
    - gold.disease_name (case-insensitive) when predicted is a plain NL name
    - an Orphadata fuzzy-match (score ≥ 90) to any cross-mapped ORPHA of gold,
      when predicted is a plain NL name

    The last two paths support agents whose adapter does not convert NL output
    to ORPHA IDs before logging (e.g. DeepRare's stock parser emits names like
    "KBG Syndrome" verbatim). 2026-05-16 patch.
    """
    if not predicted_id:
        return False
    pid = predicted_id.strip()
    candidate_gold_ids = [
        gid for gid in (gold.omim_id, gold.orphanet_id, gold.ccrd_id) if gid
    ]
    # exact ID match
    if pid in candidate_gold_ids:
        return True
    # ID-level cross-map(OMIM ↔ ORPHA)
    if pid.startswith("OMIM:"):
        mapped = omim_to_orpha(pid)
        if any(m in candidate_gold_ids for m in mapped):
            return True
        return False
    if pid.startswith("ORPHA:"):
        mapped = orpha_to_omim(pid)
        if any(m in candidate_gold_ids for m in mapped):
            return True
        return False
    if pid.startswith("CCRD:") or pid.startswith("HP:"):
        # no NL fallback for non-disease prefixes
        return False

    # plain NL name fallback
    # (a) direct case-insensitive match to gold.disease_name
    if gold.disease_name and pid.lower() == gold.disease_name.lower():
        return True
    # (b) fuzzy-map predicted name → ORPHA via Orphadata (CACHED), then check
    #     against gold IDs and their cross-maps
    pid_orpha = _fuzzy_name_to_orpha(pid)
    if pid_orpha:
        if pid_orpha in candidate_gold_ids:
            return True
        mapped_to_omim = orpha_to_omim(pid_orpha)
        if any(m in candidate_gold_ids for m in mapped_to_omim):
            return True
    return False


@lru_cache(maxsize=200000)
def _fuzzy_name_to_orpha(pid: str) -> Optional[str]:
    """Cached fuzzy ORPHA mapping for a NL disease name (threshold=90).

    Without this cache, aggregating ~260K predictions across 87 files would call
    rapidfuzz over 11K Orphadata names per record (~minutes per file). With it,
    unique names are mapped once.
    """
    try:
        tables = _orphadata_tables()
        from harness.pmc_oa.orphanet import map_diagnosis
        res = map_diagnosis(pid, tables, fuzzy_threshold=90)
        return res.get("orpha_id")
    except Exception:
        return None


@lru_cache(maxsize=1)
def _orphadata_tables() -> dict:
    """One-time process-wide parse of 53MB Orphadata XML.
    Without this cache, gold_hit_with_crossmap on N predictions does N parses
    (~5s each) and aggregation takes hours. With it, single parse on first hit.
    """
    from harness.pmc_oa.orphanet import parse_orphadata
    return parse_orphadata()


def gold_hit_with_variants(predicted, gold) -> bool:
    """Like `gold_hit_with_crossmap` but accepts either a single ID string
    OR a list of tied candidates. Returns True if ANY variant hits.

    Use this when adapter logs `extra["ranked_predictions_variants"]`
    (2026-05-19 RareBench fuzzy-tie fix).
    """
    if isinstance(predicted, str):
        return gold_hit_with_crossmap(predicted, gold)
    if isinstance(predicted, (list, tuple)):
        return any(gold_hit_with_crossmap(p, gold) for p in predicted if p)
    return False


__all__ = [
    "omim_to_orpha",
    "orpha_to_omim",
    "equivalent_ids",
    "gold_hit_with_crossmap",
    "gold_hit_with_variants",
]

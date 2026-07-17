"""HPO natural-language phrase → canonical HP:xxxxxxx ID (FIX D3, 2026-05-15).

Thin wrapper around `harness.metrics.hpo_normalization` exposing the
`phrase_to_hp_id` / `phrases_to_hp_ids` API requested by the round-2 phase-0
bug-fix plan (round2_plan.md § 复盘 ①).

Why a separate module instead of just using `normalize_phrase`:
- Round-2 plan explicitly asked for `harness.metrics.hpo_phrase_to_id` so the
  adapter patches (lirical.py, vc_rdagent.py) have a stable import path.
- This module also adds a small batching convenience that filters out misses
  by default — adapters that need HPO IDs (LIRICAL/VC-RDAgent) cannot accept
  None entries.

Uses rapidfuzz fuzzy matching (threshold default 90) against the hp.obo
name + synonym index (~17k terms). Cached after first call.

Example:
    >>> from harness.metrics.hpo_phrase_to_id import phrase_to_hp_id
    >>> phrase_to_hp_id("microcephaly")
    'HP:0000252'
    >>> phrase_to_hp_id("intellectual disability")
    'HP:0001249'
    >>> phrase_to_hp_id("nonsense rambling")  # below threshold
    None
"""

from __future__ import annotations

from typing import List, Optional

from harness.metrics.hpo_normalization import normalize_phrase

# Re-export the workhorse from hpo_normalization. Naming follows the round-2
# plan's "phrase_to_hp_id" convention; the underlying implementation is shared.
DEFAULT_THRESHOLD = 90


def phrase_to_hp_id(phrase: str, threshold: int = DEFAULT_THRESHOLD) -> Optional[str]:
    """Map a single free-text phenotypic phrase to its canonical HP ID, or None.

    Args:
        phrase: e.g., "progressive proximal muscle weakness".
        threshold: rapidfuzz `token_set_ratio` cutoff (0-100). Default 90.

    Returns:
        HP:xxxxxxx string if a match (exact or fuzzy ≥ threshold) is found,
        otherwise None.
    """
    return normalize_phrase(phrase, threshold=threshold)


def phrases_to_hp_ids(
    phrases: List[str],
    threshold: int = DEFAULT_THRESHOLD,
    *,
    drop_misses: bool = True,
    dedupe: bool = True,
) -> List[str]:
    """Map a list of phrases to HP IDs.

    Args:
        phrases: list of free-text phenotypic phrases.
        threshold: fuzzy match cutoff.
        drop_misses: if True (default), entries that don't resolve to any HP ID
            are dropped. If False, returns parallel list with None for misses.
            (Note: when False, return type is List[Optional[str]] in practice;
            callers using LIRICAL/VC-RDAgent should keep drop_misses=True.)
        dedupe: if True (default), removes duplicate HP IDs while preserving
            first-seen order.

    Returns:
        List of HP:xxxxxxx strings (with drop_misses=True). May be empty.
    """
    out: List[str] = []
    seen: set[str] = set()
    for p in phrases:
        hp = normalize_phrase(p, threshold=threshold)
        if hp is None:
            if drop_misses:
                continue
            # mypy/type-checkers will complain — caller asked for misses.
            out.append(None)  # type: ignore[arg-type]
            continue
        if dedupe and hp in seen:
            continue
        seen.add(hp)
        out.append(hp)
    return out


__all__ = ["phrase_to_hp_id", "phrases_to_hp_ids", "DEFAULT_THRESHOLD"]

"""Accuracy metrics: Recall@k, Median Rank, MRR.

Matching strategy (v1):
- Prediction is `List[str]` of disease IDs (any of OMIM:/ORPHA:/CCRD: or free
  name).
- Gold `GoldLabel` carries multiple parallel IDs from different ontologies.
- A predicted ID HITS the gold iff:
    (a) it has a known prefix and equals the gold's same-prefix ID, OR
    (b) it has no prefix but case-insensitively matches gold.disease_name.
- Cross-ontology mapping (OMIM ↔ ORPHA via Orphadata) is a separate concern
  handled by `harness.metrics.cross_map` (todo).

We deliberately do NOT do fuzzy / synonym / hypernym matching at this layer —
those are evaluator-specific (LLM-judge for RareArena's 0/1/2 scoring;
ontology-walk for hypernym credit). Keep this layer deterministic.
"""

from __future__ import annotations

from statistics import median
from typing import List, Optional, Sequence

from harness.canonical_case import GoldLabel


def is_hit(predicted_id: str, gold: GoldLabel) -> bool:
    """Return True iff predicted_id matches gold via any parallel ID system."""
    pid = predicted_id.strip()
    if not pid:
        return False

    if pid.startswith("OMIM:") and gold.omim_id:
        return pid == gold.omim_id
    if pid.startswith("ORPHA:") and gold.orphanet_id:
        return pid == gold.orphanet_id
    if pid.startswith("CCRD:") and gold.ccrd_id:
        return pid == gold.ccrd_id

    # name fallback (case-insensitive exact)
    if gold.disease_name and pid.lower() == gold.disease_name.lower():
        return True

    return False


def rank_of_hit(predictions: Sequence[str], gold: GoldLabel) -> Optional[int]:
    """First 1-indexed rank where a prediction hits the gold; None if no hit."""
    for i, p in enumerate(predictions, start=1):
        if is_hit(p, gold):
            return i
    return None


def recall_at_k(
    predictions: Sequence[Sequence[str]],
    golds: Sequence[GoldLabel],
    k: int,
) -> float:
    """Fraction of cases where the gold appears within top-k predictions."""
    if not predictions:
        return 0.0
    if len(predictions) != len(golds):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions vs {len(golds)} golds"
        )
    hits = 0
    for preds, gold in zip(predictions, golds):
        if rank_of_hit(preds[:k], gold) is not None:
            hits += 1
    return hits / len(predictions)


def median_rank(
    predictions: Sequence[Sequence[str]],
    golds: Sequence[GoldLabel],
    miss_value: Optional[int] = None,
) -> float:
    """Median rank of the gold across cases.

    For cases where gold is not in any prediction:
    - If miss_value is None, treat as `len(preds) + 1` (worst possible).
    - Otherwise use the explicit miss_value (e.g., 100 for capped ranking).
    """
    if not predictions:
        return float("inf")
    ranks: List[int] = []
    for preds, gold in zip(predictions, golds):
        r = rank_of_hit(preds, gold)
        if r is not None:
            ranks.append(r)
        else:
            ranks.append(miss_value if miss_value is not None else len(preds) + 1)
    return median(ranks)


def mrr(
    predictions: Sequence[Sequence[str]],
    golds: Sequence[GoldLabel],
) -> float:
    """Mean reciprocal rank.

    Cases with no hit contribute 0 to the sum (standard MRR convention).
    """
    if not predictions:
        return 0.0
    rr_sum = 0.0
    for preds, gold in zip(predictions, golds):
        r = rank_of_hit(preds, gold)
        if r is not None:
            rr_sum += 1.0 / r
    return rr_sum / len(predictions)


def recall_at_k_table(
    predictions: Sequence[Sequence[str]],
    golds: Sequence[GoldLabel],
    ks: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, float]:
    """Convenience: Recall@k for multiple ks at once. Returns dict like
    {'recall@1': 0.32, 'recall@3': 0.48, 'recall@5': 0.55, 'recall@10': 0.61}.
    """
    return {f"recall@{k}": recall_at_k(predictions, golds, k) for k in ks}


__all__ = [
    "is_hit",
    "rank_of_hit",
    "recall_at_k",
    "median_rank",
    "mrr",
    "recall_at_k_table",
]

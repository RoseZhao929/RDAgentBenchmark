"""Phenotype extraction metrics: HPO term-level P/R/F1.

For Pillar 1 (phenotype extraction): agent extracts HPO terms from free text,
we compare against `gold_hpo_terms` in canonical case.

Three matching modes:
- `exact`: HPO ID string equality
- `ancestor`: predicted ID is an ancestor of (or equal to) any gold ID
  (RAG-HPO style: gives partial credit for over-broad terms)
- `descendant`: predicted ID is descendant of (or equal to) any gold ID

Default is `exact`. Ancestor/descendant modes require an HPO ontology graph
which we lazily load from `hp.obo` (TODO: implement `hpo_graph.py`).
"""

from __future__ import annotations

from typing import Iterable, List, Literal, Sequence, Set

from harness.canonical_case import HpoTerm

MatchMode = Literal["exact"]   # ancestor/descendant todo


def _ids(terms: Iterable[HpoTerm]) -> Set[str]:
    return {t.id for t in terms if not t.negated}


def hpo_prf1(
    predicted: Sequence[HpoTerm],
    gold: Sequence[HpoTerm],
    mode: MatchMode = "exact",
) -> dict[str, float]:
    """Per-case HPO precision/recall/F1.

    Returns dict {'precision': p, 'recall': r, 'f1': f, 'tp': k, 'fp': k, 'fn': k}.

    Negated terms (excluded findings) are dropped from both sides for v1.
    """
    if mode != "exact":
        raise NotImplementedError(f"Match mode {mode!r} not yet implemented")

    pred_ids = _ids(predicted)
    gold_ids = _ids(gold)

    tp = len(pred_ids & gold_ids)
    fp = len(pred_ids - gold_ids)
    fn = len(gold_ids - pred_ids)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def aggregate_hpo_prf1(
    case_metrics: Sequence[dict[str, float]],
    aggregate: Literal["micro", "macro"] = "micro",
) -> dict[str, float]:
    """Roll up per-case PRF1 to a corpus number.

    - `micro`: sum TP/FP/FN across cases, then compute global P/R/F1
              (weighs cases proportional to # of gold terms — RareBench convention)
    - `macro`: simple mean of per-case PRF1 (each case weighted equally)
    """
    if not case_metrics:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    if aggregate == "micro":
        tp = sum(m["tp"] for m in case_metrics)
        fp = sum(m["fp"] for m in case_metrics)
        fn = sum(m["fn"] for m in case_metrics)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return {"precision": p, "recall": r, "f1": f1}

    # macro
    n = len(case_metrics)
    return {
        "precision": sum(m["precision"] for m in case_metrics) / n,
        "recall": sum(m["recall"] for m in case_metrics) / n,
        "f1": sum(m["f1"] for m in case_metrics) / n,
    }


__all__ = ["hpo_prf1", "aggregate_hpo_prf1", "MatchMode"]

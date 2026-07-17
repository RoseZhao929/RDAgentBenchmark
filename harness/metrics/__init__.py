"""Metric library for Rare Disease Agent Benchmark.

Tier 1 (must-report):
- accuracy: Recall@k, Median Rank, MRR
- phenotype: HPO P/R/F1

Tier 2 (recommended):
- calibration: Brier, ECE, Confidence AUROC, Reliability diagram bins
- reliability: pass^k (from-runs and unbiased estimator)
- cost: Cost-Normalized Accuracy, Cost-Per-Success, latency aggregations

Tier 3 (exploratory):
- (todo) faithfulness: CoT-faithfulness, FActScore-style atomic facts
- (todo) cross_map: OMIM ↔ ORPHA mapping via Orphadata (already in harness.pmc_oa.orphanet for diagnoses)
"""

from harness.metrics.accuracy import (
    is_hit,
    median_rank,
    mrr,
    rank_of_hit,
    recall_at_k,
    recall_at_k_table,
)
from harness.metrics.calibration import (
    brier_score,
    confidence_discrimination_auroc,
    expected_calibration_error,
    reliability_diagram_bins,
)
from harness.metrics.cost import (
    aggregate_cost,
    aggregate_latency,
    cost_normalized_accuracy,
    cost_per_success,
)
from harness.metrics.hpo_normalization import (
    normalize_phrase,
    normalize_phrases,
)
from harness.metrics.phenotype import (
    MatchMode,
    aggregate_hpo_prf1,
    hpo_prf1,
)
from harness.metrics.reliability import (
    aggregate_pass_at_k,
    pass_at_k_from_runs,
    pass_at_k_unbiased,
)

__all__ = [
    # accuracy
    "is_hit", "rank_of_hit", "recall_at_k", "median_rank", "mrr",
    "recall_at_k_table",
    # phenotype
    "hpo_prf1", "aggregate_hpo_prf1", "MatchMode",
    "normalize_phrase", "normalize_phrases",
    # calibration
    "brier_score", "expected_calibration_error",
    "reliability_diagram_bins", "confidence_discrimination_auroc",
    # reliability
    "pass_at_k_from_runs", "pass_at_k_unbiased", "aggregate_pass_at_k",
    # cost
    "cost_normalized_accuracy", "cost_per_success",
    "aggregate_cost", "aggregate_latency",
]

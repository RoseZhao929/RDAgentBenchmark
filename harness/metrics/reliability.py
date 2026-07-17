"""Reliability metrics: pass^k and friends (τ-bench style).

pass^k = probability that k independent i.i.d. runs of the same case all
succeed. This is the metric Anthropic's model cards use to surface agent
unreliability — GPT-4o on τ-bench retail pass^8 was below 25% even when single-
run accuracy was reasonable.

Computation modes:
- `pass_at_k_from_runs(per_case_outcomes)`: given a list of per-case run results
  where each entry is a list of k boolean outcomes, return the fraction of cases
  where ALL k runs succeeded. This requires actually running the agent k times
  on each case.
- `pass_at_k_unbiased(n_correct, n_total, k)`: HumanEval-style unbiased
  estimator (1 - C(n-c,k)/C(n,k)). Use this when you ran the agent N times
  per case and want pass^k for k <= N.
"""

from __future__ import annotations

from math import comb
from typing import Sequence


def pass_at_k_from_runs(per_case_outcomes: Sequence[Sequence[bool]]) -> float:
    """Fraction of cases where all-k independent runs succeeded.

    `per_case_outcomes[i]` is the list of run outcomes for case i; all must
    have the same length k.
    """
    if not per_case_outcomes:
        return float("nan")
    k = len(per_case_outcomes[0])
    for case_runs in per_case_outcomes:
        if len(case_runs) != k:
            raise ValueError("all cases must have the same number of runs")
    full_passes = sum(1 for runs in per_case_outcomes if all(runs))
    return full_passes / len(per_case_outcomes)


def pass_at_k_unbiased(n_total: int, n_correct: int, k: int) -> float:
    """Unbiased pass^k estimator (HumanEval / Kulal et al. 2019 form).

    Given n_total independent runs on a case, n_correct of which succeeded,
    estimate the probability that k random draws all succeed.

    Formula (Codex paper Eq.1 reversed for ALL-PASS semantics):
        pass^k = 1 - C(n - c, k) / C(n, k)   if (n - c) >= k else 1.0

    For pass^k of an ALL-MUST-PASS interpretation we use:
        pass^k = C(c, k) / C(n, k)   if c >= k else 0.0
    """
    if k <= 0 or k > n_total:
        raise ValueError("k must be in [1, n_total]")
    if n_correct < k:
        return 0.0
    return comb(n_correct, k) / comb(n_total, k)


def aggregate_pass_at_k(
    per_case_counts: Sequence[tuple[int, int]],
    k: int,
) -> float:
    """Average unbiased pass^k across cases.

    `per_case_counts[i] = (n_total_runs, n_correct)` for case i.
    """
    if not per_case_counts:
        return float("nan")
    vals = []
    for n, c in per_case_counts:
        if k > n:
            continue
        vals.append(pass_at_k_unbiased(n, c, k))
    if not vals:
        return float("nan")
    return sum(vals) / len(vals)


__all__ = [
    "pass_at_k_from_runs",
    "pass_at_k_unbiased",
    "aggregate_pass_at_k",
]

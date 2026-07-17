"""Cost-related metrics (Tier 2).

- Cost-Normalized Accuracy (CLEAR framework): accuracy / USD
- Cost-Per-Success: total USD / number of correct predictions
- Token & latency aggregations

Per CLEAR framework (arXiv 2511.14136). Reports three independent cost axes
that should NOT be conflated:
1. Deterministic API token cost (from provider usage object)
2. Wall-clock latency (per-call ms summed)
3. Simulated diagnostic-test cost (from published fee schedules — for MAI-DxO
   style budget-aware orchestration only)
"""

from __future__ import annotations

from typing import Sequence


def cost_normalized_accuracy(accuracy: float, total_cost_usd: float) -> float:
    """Accuracy per USD. Returns 0 if cost is 0 to avoid div-by-zero."""
    if total_cost_usd <= 0:
        return 0.0
    return accuracy / total_cost_usd


def cost_per_success(total_cost_usd: float, n_correct: int) -> float:
    """Average USD spent per correctly diagnosed case. inf if no correct."""
    if n_correct <= 0:
        return float("inf")
    return total_cost_usd / n_correct


def aggregate_cost(per_case_cost_usd: Sequence[float]) -> dict[str, float]:
    """Total / mean / median / p95 of per-case cost in USD."""
    if not per_case_cost_usd:
        return {"total": 0.0, "mean": 0.0, "median": 0.0, "p95": 0.0}
    sorted_costs = sorted(per_case_cost_usd)
    n = len(sorted_costs)
    return {
        "total": sum(sorted_costs),
        "mean": sum(sorted_costs) / n,
        "median": sorted_costs[n // 2],
        "p95": sorted_costs[min(int(0.95 * n), n - 1)],
    }


def aggregate_latency(per_case_latency_ms: Sequence[int]) -> dict[str, float]:
    """Mean / median / p50 / p95 / p99 latency in ms."""
    if not per_case_latency_ms:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0, "p99": 0.0}
    sorted_lat = sorted(per_case_latency_ms)
    n = len(sorted_lat)
    return {
        "mean": sum(sorted_lat) / n,
        "median": sorted_lat[n // 2],
        "p95": sorted_lat[min(int(0.95 * n), n - 1)],
        "p99": sorted_lat[min(int(0.99 * n), n - 1)],
    }


__all__ = [
    "cost_normalized_accuracy",
    "cost_per_success",
    "aggregate_cost",
    "aggregate_latency",
]

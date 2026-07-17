"""Calibration metrics: Brier score, Expected Calibration Error (ECE).

Used for the Tier 2 calibration analysis (H6 reasoning-mode hypothesis).

Inputs are pairs of (predicted_probability, binary_correctness):
- predicted_probability: agent's confidence that its top-1 prediction is correct,
                         in [0, 1]
- binary_correctness:    1 if the agent's top-1 actually matches gold, else 0

Reference: Rivera et al., JAMIA Vol 32 No 1 — recommended ECE bins=10, Brier,
confidence discrimination AUROC threshold ≥0.7 for medical applications.
"""

from __future__ import annotations

from typing import Sequence


def brier_score(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean (p - y)^2 over cases. Lower is better. Range [0, 1].

    p in [0,1], y in {0,1}.
    """
    if len(probs) != len(outcomes):
        raise ValueError("length mismatch")
    if not probs:
        return float("nan")
    return sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / len(probs)


def expected_calibration_error(
    probs: Sequence[float],
    outcomes: Sequence[int],
    n_bins: int = 10,
) -> float:
    """Standard ECE with equal-width bins.

    ECE = sum_b (|b| / N) * |acc_b - conf_b|

    Lower is better. 0 = perfect calibration.
    """
    if len(probs) != len(outcomes):
        raise ValueError("length mismatch")
    n = len(probs)
    if n == 0:
        return float("nan")

    # bin edges 0..1
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    bin_acc = [0.0] * n_bins
    bin_conf = [0.0] * n_bins
    bin_count = [0] * n_bins

    for p, y in zip(probs, outcomes):
        # find bin (right-inclusive at top)
        idx = min(int(p * n_bins), n_bins - 1)
        bin_count[idx] += 1
        bin_acc[idx] += y
        bin_conf[idx] += p

    ece = 0.0
    for i in range(n_bins):
        if bin_count[i] == 0:
            continue
        acc_i = bin_acc[i] / bin_count[i]
        conf_i = bin_conf[i] / bin_count[i]
        ece += (bin_count[i] / n) * abs(acc_i - conf_i)
    return ece


def reliability_diagram_bins(
    probs: Sequence[float],
    outcomes: Sequence[int],
    n_bins: int = 10,
) -> list[dict]:
    """Return per-bin stats for plotting a reliability diagram.

    Each entry: {bin_lo, bin_hi, count, mean_confidence, accuracy, gap}
    """
    n = len(probs)
    if n == 0:
        return []
    out = []
    for i in range(n_bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        bucket = [(p, y) for p, y in zip(probs, outcomes) if lo <= p < hi or (i == n_bins - 1 and p == 1.0)]
        c = len(bucket)
        if c == 0:
            out.append({"bin_lo": lo, "bin_hi": hi, "count": 0,
                        "mean_confidence": None, "accuracy": None, "gap": None})
            continue
        mean_p = sum(p for p, _ in bucket) / c
        acc = sum(y for _, y in bucket) / c
        out.append({"bin_lo": lo, "bin_hi": hi, "count": c,
                    "mean_confidence": mean_p, "accuracy": acc,
                    "gap": acc - mean_p})
    return out


def confidence_discrimination_auroc(
    probs: Sequence[float],
    outcomes: Sequence[int],
) -> float:
    """AUROC: how well does confidence rank correct vs. incorrect predictions?

    1.0 = confidence perfectly discriminates; 0.5 = random; <0.5 = anti-correlated.
    Implementation: Mann-Whitney U statistic.
    """
    pos = [p for p, y in zip(probs, outcomes) if y == 1]
    neg = [p for p, y in zip(probs, outcomes) if y == 0]
    n_pos, n_neg = len(pos), len(neg)
    if n_pos == 0 or n_neg == 0:
        return float("nan")

    count = 0.0
    for pp in pos:
        for nn in neg:
            if pp > nn:
                count += 1.0
            elif pp == nn:
                count += 0.5
    return count / (n_pos * n_neg)


__all__ = [
    "brier_score",
    "expected_calibration_error",
    "reliability_diagram_bins",
    "confidence_discrimination_auroc",
]

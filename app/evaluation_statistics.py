"""Statistical utilities for production AI evaluation.

The module intentionally uses the Python standard library so CI evaluation can run
without adding heavyweight scientific dependencies. It provides bootstrap confidence
intervals and paired bootstrap comparisons suitable for baseline-vs-candidate gates.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from statistics import mean
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class ConfidenceInterval:
    """A point estimate with a two-sided confidence interval."""

    estimate: float
    lower: float
    upper: float
    confidence: float


@dataclass(frozen=True)
class PairedComparison:
    """Bootstrap comparison of candidate and baseline per-example scores."""

    delta: float
    lower: float
    upper: float
    probability_improved: float
    iterations: int


def _percentile(values: Sequence[float], q: float) -> float:
    """Return a linearly interpolated percentile for sorted or unsorted values."""
    if not values:
        raise ValueError("values must not be empty")
    if not 0 <= q <= 1:
        raise ValueError("q must be between 0 and 1")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * q
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    fraction = index - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def bootstrap_ci(
    values: Iterable[float],
    *,
    statistic: Callable[[Sequence[float]], float] = mean,
    confidence: float = 0.95,
    iterations: int = 2000,
    seed: int = 42,
) -> ConfidenceInterval:
    """Estimate a bootstrap confidence interval for a scalar statistic.

    Args:
        values: Per-example measurements.
        statistic: Statistic applied to each resample. Defaults to arithmetic mean.
        confidence: Two-sided confidence level.
        iterations: Number of bootstrap resamples.
        seed: Reproducibility seed.
    """
    sample = list(values)
    if not sample:
        raise ValueError("values must not be empty")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    if iterations < 100:
        raise ValueError("iterations must be at least 100")

    rng = random.Random(seed)
    n = len(sample)
    estimates = [
        statistic([sample[rng.randrange(n)] for _ in range(n)])
        for _ in range(iterations)
    ]
    alpha = (1 - confidence) / 2
    return ConfidenceInterval(
        estimate=float(statistic(sample)),
        lower=float(_percentile(estimates, alpha)),
        upper=float(_percentile(estimates, 1 - alpha)),
        confidence=confidence,
    )


def paired_bootstrap_compare(
    baseline: Sequence[float],
    candidate: Sequence[float],
    *,
    confidence: float = 0.95,
    iterations: int = 4000,
    seed: int = 42,
) -> PairedComparison:
    """Compare candidate against baseline using paired bootstrap resampling.

    Pairing preserves case-level difficulty and is therefore preferred over comparing
    two independently bootstrapped means when both systems evaluated the same golden set.
    Positive deltas mean the candidate is better.
    """
    if len(baseline) != len(candidate):
        raise ValueError("baseline and candidate must have equal length")
    if not baseline:
        raise ValueError("scores must not be empty")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    if iterations < 100:
        raise ValueError("iterations must be at least 100")

    rng = random.Random(seed)
    n = len(baseline)
    deltas: list[float] = []
    for _ in range(iterations):
        indexes = [rng.randrange(n) for _ in range(n)]
        base_mean = mean(baseline[i] for i in indexes)
        cand_mean = mean(candidate[i] for i in indexes)
        deltas.append(float(cand_mean - base_mean))

    alpha = (1 - confidence) / 2
    observed_delta = float(mean(candidate) - mean(baseline))
    probability_improved = sum(delta > 0 for delta in deltas) / len(deltas)
    return PairedComparison(
        delta=observed_delta,
        lower=float(_percentile(deltas, alpha)),
        upper=float(_percentile(deltas, 1 - alpha)),
        probability_improved=probability_improved,
        iterations=iterations,
    )

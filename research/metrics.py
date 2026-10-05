"""Research-grade metrics for EvalForge experiments.

This module deliberately uses the Python standard library so experiment
analysis remains easy to reproduce in minimal environments.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from random import Random
from statistics import mean
from typing import Iterable, Sequence


Label = str


@dataclass(frozen=True)
class BinaryMetrics:
    accuracy: float
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    false_negative_rate: float
    tp: int
    fp: int
    tn: int
    fn: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def binary_metrics(
    gold: Sequence[Label],
    pred: Sequence[Label],
    *,
    positive_label: Label = "fail",
) -> BinaryMetrics:
    if len(gold) != len(pred):
        raise ValueError("gold and pred must have the same length")
    if not gold:
        raise ValueError("gold and pred must not be empty")

    tp = fp = tn = fn = 0
    for g, p in zip(gold, pred):
        g_pos = g == positive_label
        p_pos = p == positive_label
        if g_pos and p_pos:
            tp += 1
        elif not g_pos and p_pos:
            fp += 1
        elif not g_pos and not p_pos:
            tn += 1
        else:
            fn += 1

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)

    return BinaryMetrics(
        accuracy=_safe_div(tp + tn, len(gold)),
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=_safe_div(fp, fp + tn),
        false_negative_rate=_safe_div(fn, fn + tp),
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
    )


def paired_bootstrap_difference(
    gold: Sequence[Label],
    pred_a: Sequence[Label],
    pred_b: Sequence[Label],
    *,
    metric: str = "f1",
    iterations: int = 2000,
    seed: int = 42,
    positive_label: Label = "fail",
) -> dict[str, float]:
    """Bootstrap a paired metric difference: system B minus system A."""
    if not (len(gold) == len(pred_a) == len(pred_b)):
        raise ValueError("gold, pred_a, and pred_b must have the same length")
    if not gold:
        raise ValueError("inputs must not be empty")
    if iterations < 100:
        raise ValueError("iterations must be at least 100")

    rng = Random(seed)
    n = len(gold)
    diffs: list[float] = []

    for _ in range(iterations):
        idx = [rng.randrange(n) for _ in range(n)]
        g = [gold[i] for i in idx]
        a = [pred_a[i] for i in idx]
        b = [pred_b[i] for i in idx]
        ma = getattr(binary_metrics(g, a, positive_label=positive_label), metric)
        mb = getattr(binary_metrics(g, b, positive_label=positive_label), metric)
        diffs.append(mb - ma)

    diffs.sort()
    lo = diffs[int(0.025 * (iterations - 1))]
    hi = diffs[int(0.975 * (iterations - 1))]
    observed_a = getattr(binary_metrics(gold, pred_a, positive_label=positive_label), metric)
    observed_b = getattr(binary_metrics(gold, pred_b, positive_label=positive_label), metric)

    return {
        "system_a": observed_a,
        "system_b": observed_b,
        "difference_b_minus_a": observed_b - observed_a,
        "bootstrap_mean_difference": mean(diffs),
        "ci95_low": lo,
        "ci95_high": hi,
    }

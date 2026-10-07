"""Research-grade metrics for EvalForge experiments.

This module deliberately uses the Python standard library so experiment
analysis remains easy to reproduce in minimal environments.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import comb, sqrt
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


# ---------------------------------------------------------------------------
# Null-safe metrics used by `research.run`.
#
# Conventions (documented in research/METRICS.md):
# * A prediction of ``None`` means the system produced no decision (abstention,
#   unparseable judge output, or a crash). It always counts as an error for
#   accuracy, as a false negative when the gold label is positive, and is never
#   counted as a false positive.
# * A metric whose denominator is zero is ``None`` (undefined), never 0.0.
# ---------------------------------------------------------------------------

PRIMARY_METRICS: tuple[str, ...] = (
    "accuracy",
    "precision",
    "recall",
    "f1",
    "macro_f1",
    "false_positive_rate",
    "false_negative_rate",
)


def _div(num: float, den: float) -> float | None:
    return num / den if den else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    # A defined zero on either side means the class is entirely missed (or never correct): F1 = 0.
    if precision == 0 or recall == 0:
        return 0.0
    if precision is None or recall is None:
        return None
    return 2 * precision * recall / (precision + recall)


def _class_f1(gold: Sequence[Label], pred: Sequence[Label | None], label: Label) -> float | None:
    tp = sum(1 for g, p in zip(gold, pred) if g == label and p == label)
    fp = sum(1 for g, p in zip(gold, pred) if g != label and p == label)
    fn = sum(1 for g, p in zip(gold, pred) if g == label and p != label)
    return _f1(_div(tp, tp + fp), _div(tp, tp + fn))


def classification_metrics(
    gold: Sequence[Label],
    pred: Sequence[Label | None],
    *,
    positive_label: Label = "fail",
    negative_label: Label = "pass",
) -> dict[str, float | int | None]:
    if len(gold) != len(pred):
        raise ValueError("gold and pred must have the same length")
    if not gold:
        raise ValueError("gold and pred must not be empty")

    tp = fp = tn = fn = abstain_pos = abstain_neg = 0
    for g, p in zip(gold, pred):
        if p is None:
            if g == positive_label:
                abstain_pos += 1
            else:
                abstain_neg += 1
            continue
        if g == positive_label:
            tp += p == positive_label
            fn += p != positive_label
        else:
            fp += p == positive_label
            tn += p != positive_label

    n = len(gold)
    gold_pos = tp + fn + abstain_pos
    gold_neg = fp + tn + abstain_neg
    precision = _div(tp, tp + fp)
    recall = _div(tp, gold_pos)
    f1_pos = _f1(precision, recall)
    f1_neg = _class_f1(gold, pred, negative_label)
    macro = None if f1_pos is None or f1_neg is None else (f1_pos + f1_neg) / 2

    return {
        "n": n,
        "n_decided": n - abstain_pos - abstain_neg,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn + abstain_pos,
        "abstained": abstain_pos + abstain_neg,
        "accuracy": (tp + tn) / n,
        "precision": precision,
        "recall": recall,
        "f1": f1_pos,
        "macro_f1": macro,
        "false_positive_rate": _div(fp, gold_neg),
        "false_negative_rate": _div(fn + abstain_pos, gold_pos),
    }


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile of an already sorted sequence (0 <= q <= 1)."""
    if not sorted_values:
        raise ValueError("percentile of empty sequence")
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _resample_indices(n: int, iterations: int, seed: int) -> list[list[int]]:
    rng = Random(seed)
    return [[rng.randrange(n) for _ in range(n)] for _ in range(iterations)]


def bootstrap_confidence_intervals(
    gold: Sequence[Label],
    pred: Sequence[Label | None],
    *,
    metrics: Sequence[str] = PRIMARY_METRICS,
    iterations: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict[str, dict[str, float | int | None]]:
    """Percentile bootstrap CIs over cases. Undefined resamples are skipped and counted."""
    if iterations < 100:
        raise ValueError("iterations must be at least 100")
    point = classification_metrics(gold, pred)
    samples: dict[str, list[float]] = {m: [] for m in metrics}
    for idx in _resample_indices(len(gold), iterations, seed):
        resampled = classification_metrics([gold[i] for i in idx], [pred[i] for i in idx])
        for m in metrics:
            value = resampled[m]
            if value is not None:
                samples[m].append(float(value))
    out: dict[str, dict[str, float | int | None]] = {}
    for m in metrics:
        values = sorted(samples[m])
        out[m] = {
            "point": point[m],
            "ci_low": percentile(values, alpha / 2) if values else None,
            "ci_high": percentile(values, 1 - alpha / 2) if values else None,
            "valid_resamples": len(values),
            "iterations": iterations,
            "seed": seed,
        }
    return out


def paired_bootstrap(
    gold: Sequence[Label],
    pred_a: Sequence[Label | None],
    pred_b: Sequence[Label | None],
    *,
    metrics: Sequence[str] = ("accuracy", "f1", "macro_f1", "false_positive_rate"),
    iterations: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict[str, dict[str, float | int | None]]:
    """Paired bootstrap of metric(B) - metric(A) on identical resampled cases."""
    if not (len(gold) == len(pred_a) == len(pred_b)):
        raise ValueError("gold, pred_a, and pred_b must have the same length")
    if iterations < 100:
        raise ValueError("iterations must be at least 100")
    point_a = classification_metrics(gold, pred_a)
    point_b = classification_metrics(gold, pred_b)
    diffs: dict[str, list[float]] = {m: [] for m in metrics}
    for idx in _resample_indices(len(gold), iterations, seed):
        g = [gold[i] for i in idx]
        ma = classification_metrics(g, [pred_a[i] for i in idx])
        mb = classification_metrics(g, [pred_b[i] for i in idx])
        for m in metrics:
            if ma[m] is not None and mb[m] is not None:
                diffs[m].append(float(mb[m]) - float(ma[m]))
    out: dict[str, dict[str, float | int | None]] = {}
    for m in metrics:
        values = sorted(diffs[m])
        a, b = point_a[m], point_b[m]
        out[m] = {
            "system_a": a,
            "system_b": b,
            "difference_b_minus_a": None if a is None or b is None else float(b) - float(a),
            "ci_low": percentile(values, alpha / 2) if values else None,
            "ci_high": percentile(values, 1 - alpha / 2) if values else None,
            "valid_resamples": len(values),
        }
    return out


def _binomial_two_sided_p(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2**n
    return min(1.0, 2 * tail)


def mcnemar_exact(
    gold: Sequence[Label],
    pred_a: Sequence[Label | None],
    pred_b: Sequence[Label | None],
) -> dict[str, float | int]:
    """Exact (binomial) McNemar test on per-case correctness."""
    if not (len(gold) == len(pred_a) == len(pred_b)):
        raise ValueError("gold, pred_a, and pred_b must have the same length")
    only_a = sum(1 for g, a, b in zip(gold, pred_a, pred_b) if a == g and b != g)
    only_b = sum(1 for g, a, b in zip(gold, pred_a, pred_b) if a != g and b == g)
    return {
        "a_correct_b_wrong": only_a,
        "a_wrong_b_correct": only_b,
        "discordant": only_a + only_b,
        "p_value": _binomial_two_sided_p(only_a, only_a + only_b),
    }


def cohen_kappa(x: Sequence[Label | None], y: Sequence[Label | None]) -> float | None:
    """Cohen's kappa over pairs where both raters gave a label; None if undefined."""
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    labels = {a for a, _ in pairs} | {b for _, b in pairs}
    expected = sum(
        (sum(1 for a, _ in pairs if a == label) / n) * (sum(1 for _, b in pairs if b == label) / n)
        for label in labels
    )
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)

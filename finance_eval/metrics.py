"""Metrics aggregation for finance evaluation runs."""

from __future__ import annotations

import math
import random
from typing import Any

from finance_eval.schema import CaseResult, RunMetrics
from finance_eval.taxonomy import FinanceFailureCode as F
from finance_eval.taxonomy import is_critical

_NONE = F.FIN_NONE.value


def _rate(n: int, d: int) -> float | None:
    """Return n/d, or None when the denominator is zero (never invent 0.0)."""
    if d == 0:
        return None
    return n / d


def bootstrap_ci(values: list[float], iterations: int = 1000, seed: int = 42) -> tuple[float, float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    samples: list[float] = []
    for _ in range(iterations):
        draw = [values[rng.randrange(n)] for _ in range(n)]
        samples.append(sum(draw) / n)
    samples.sort()
    lo = samples[int(0.025 * (iterations - 1))]
    hi = samples[int(0.975 * (iterations - 1))]
    return (lo, hi)


def planted_detection_counts(
    results: list[CaseResult],
) -> tuple[int, int, int, int] | None:
    """Confusion matrix for grader-fail vs planted_failure labels.

    Positive class = material failure.
    - planted positive: planted_failure is set and not FIN-NONE
    - predicted positive: deterministic grader did not pass

    Returns (tp, fp, tn, fn), or None when any result lacks a planted label.
    """
    if not results or any(r.planted_failure is None for r in results):
        return None
    tp = fp = tn = fn = 0
    for r in results:
        planted_fail = r.planted_failure != _NONE
        graded_fail = not r.passed
        if planted_fail and graded_fail:
            tp += 1
        elif (not planted_fail) and graded_fail:
            fp += 1
        elif (not planted_fail) and (not graded_fail):
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def detection_rates(
    tp: int, fp: int, tn: int, fn: int
) -> tuple[float | None, float | None, float | None, float | None]:
    """Precision, recall, F1, and false-positive rate from detection counts.

    F1 is 0.0 when precision or recall is a defined 0; None when either side is None.
    """
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None
    elif precision == 0.0 or recall == 0.0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    fpr = _rate(fp, fp + tn)
    return precision, recall, f1, fpr


def aggregate_metrics(
    results: list[CaseResult],
    *,
    compute_planted_detection: bool = False,
) -> RunMetrics:
    """Aggregate run metrics.

    ``precision`` / ``recall`` / ``f1`` / ``false_positive_rate`` are
    grader-vs-planted detection metrics when ``compute_planted_detection`` is
    True and every result carries ``planted_failure``. Otherwise they are
    ``None`` — never filled with tautological self-comparisons.
    """
    n = len(results)
    passed = sum(1 for r in results if r.passed)
    failure_counts: dict[str, int] = {}
    hall = calc = reason = evid = inst = crit = 0
    latencies: list[float] = []
    tokens = 0
    cost = 0.0
    has_cost = False

    for r in results:
        for code in r.failure_codes:
            failure_counts[code] = failure_counts.get(code, 0) + 1
            if code == F.FIN_HALL_006.value:
                hall += 1
            if code in {F.FIN_CALC_001.value, F.FIN_PY_008.value}:
                calc += 1
            if code in {
                F.FIN_CF_003.value,
                F.FIN_RATIO_005.value,
                F.FIN_AUD_004.value,
                F.FIN_CTRL_012.value,
                F.FIN_REV_010.value,
            }:
                reason += 1
            if code == F.FIN_EVID_009.value:
                evid += 1
            if code == F.FIN_INST_014.value:
                inst += 1
            if is_critical(code):
                crit += 1
        if r.latency_ms is not None:
            latencies.append(r.latency_ms)
        if r.prompt_tokens is not None or r.completion_tokens is not None:
            tokens += (r.prompt_tokens or 0) + (r.completion_tokens or 0)
        if r.estimated_cost_usd is not None:
            cost += r.estimated_cost_usd
            has_cost = True

    precision = recall = f1 = fpr = None
    if compute_planted_detection:
        counts = planted_detection_counts(results)
        if counts is not None:
            precision, recall, f1, fpr = detection_rates(*counts)

    return RunMetrics(
        n_cases=n,
        n_passed=passed,
        accuracy=_rate(passed, n) if n else 0.0,
        pass_rate=_rate(passed, n) if n else 0.0,
        hallucination_rate=_rate(hall, n) if n else 0.0,
        calculation_error_rate=_rate(calc, n) if n else 0.0,
        reasoning_error_rate=_rate(reason, n) if n else 0.0,
        citation_evidence_failure_rate=_rate(evid, n) if n else 0.0,
        instruction_following_failure_rate=_rate(inst, n) if n else 0.0,
        critical_error_rate=_rate(crit, n) if n else 0.0,
        mean_latency_ms=(sum(latencies) / len(latencies)) if latencies else None,
        total_tokens=tokens or None,
        estimated_cost_usd=cost if has_cost else None,
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=fpr,
        accuracy_ci95=bootstrap_ci([1.0 if r.passed else 0.0 for r in results]),
        failure_counts=failure_counts,
    )


def metrics_to_dict(m: RunMetrics) -> dict[str, Any]:
    data = m.model_dump()
    if data.get("accuracy_ci95"):
        data["accuracy_ci95"] = list(data["accuracy_ci95"])
    for k, v in list(data.items()):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            data[k] = None
    return data

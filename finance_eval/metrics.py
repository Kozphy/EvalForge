"""Metrics aggregation for finance evaluation runs."""

from __future__ import annotations

import math
import random
from typing import Any

from finance_eval.schema import CaseResult, RunMetrics
from finance_eval.taxonomy import FinanceFailureCode as F
from finance_eval.taxonomy import is_critical


def _rate(n: int, d: int) -> float:
    return 0.0 if d == 0 else n / d


def bootstrap_ci(values: list[float], iterations: int = 1000, seed: int = 42) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
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


def aggregate_metrics(results: list[CaseResult]) -> RunMetrics:
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

    # Deterministic grading compares response to gold; precision/recall here reflect
    # pass prediction consistency (pred == gold label from grade). Useful as sanity
    # metrics; accuracy remains the primary headline.
    tp = fp = tn = fn = 0
    for r in results:
        gold_pass = r.passed
        pred_pass = r.passed
        if gold_pass and pred_pass:
            tp += 1
        elif (not gold_pass) and pred_pass:
            fp += 1
        elif (not gold_pass) and (not pred_pass):
            tn += 1
        else:
            fn += 1

    precision = _rate(tp, tp + fp) if (tp + fp) else None
    recall = _rate(tp, tp + fn) if (tp + fn) else None
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    fpr = _rate(fp, fp + tn) if (fp + tn) else None

    return RunMetrics(
        n_cases=n,
        n_passed=passed,
        accuracy=_rate(passed, n),
        pass_rate=_rate(passed, n),
        hallucination_rate=_rate(hall, n),
        calculation_error_rate=_rate(calc, n),
        reasoning_error_rate=_rate(reason, n),
        citation_evidence_failure_rate=_rate(evid, n),
        instruction_following_failure_rate=_rate(inst, n),
        critical_error_rate=_rate(crit, n),
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

"""Regression comparison and finance release policy gate."""

from __future__ import annotations

from typing import Any

from finance_eval.schema import PolicyOutcome, RunMetrics
from finance_eval.taxonomy import is_critical


def compare_to_baseline(current: RunMetrics, baseline: dict[str, Any]) -> dict[str, Any]:
    b_acc = float(baseline.get("accuracy", 0))
    b_hall = float(baseline.get("hallucination_rate", 0))
    b_crit = float(baseline.get("critical_error_rate", 0))
    b_cost = baseline.get("estimated_cost_usd")
    b_lat = baseline.get("mean_latency_ms")

    regressions: list[dict[str, Any]] = []
    if current.accuracy < b_acc - 0.02:
        regressions.append(
            {
                "metric": "accuracy",
                "baseline": b_acc,
                "candidate": current.accuracy,
                "delta": current.accuracy - b_acc,
                "severity": "high",
            }
        )
    if current.hallucination_rate > b_hall + 0.02:
        regressions.append(
            {
                "metric": "hallucination_rate",
                "baseline": b_hall,
                "candidate": current.hallucination_rate,
                "delta": current.hallucination_rate - b_hall,
                "severity": "critical",
            }
        )
    if current.critical_error_rate > b_crit + 0.01:
        regressions.append(
            {
                "metric": "critical_error_rate",
                "baseline": b_crit,
                "candidate": current.critical_error_rate,
                "delta": current.critical_error_rate - b_crit,
                "severity": "critical",
            }
        )
    if b_cost is not None and current.estimated_cost_usd is not None and current.estimated_cost_usd > float(b_cost) * 1.5:
        regressions.append(
            {
                "metric": "estimated_cost_usd",
                "baseline": b_cost,
                "candidate": current.estimated_cost_usd,
                "delta": current.estimated_cost_usd - float(b_cost),
                "severity": "medium",
            }
        )
    if b_lat is not None and current.mean_latency_ms is not None and current.mean_latency_ms > float(b_lat) * 1.5:
        regressions.append(
            {
                "metric": "mean_latency_ms",
                "baseline": b_lat,
                "candidate": current.mean_latency_ms,
                "delta": current.mean_latency_ms - float(b_lat),
                "severity": "medium",
            }
        )

    baseline_failures = set((baseline.get("failure_counts") or {}).keys())
    current_failures = set(current.failure_counts.keys())
    new_failure_categories = sorted(current_failures - baseline_failures - {"FIN-NONE"})

    return {
        "regressions": regressions,
        "new_failure_categories": new_failure_categories,
        "accuracy_delta": current.accuracy - b_acc,
    }


def evaluate_policy(metrics: RunMetrics, regression: dict[str, Any] | None = None) -> dict[str, Any]:
    """Finance release policy.

    Rules (inspectable):
    - critical_error_rate > 0.05 → FAIL
    - hallucination_rate > 0.03 → HUMAN_REVIEW_REQUIRED
    - accuracy < 0.75 → FAIL
    - any critical regression vs baseline → FAIL
    - accuracy drop > 2pp without critical → WARN
    - else PASS
    """
    matched: list[dict[str, Any]] = []
    decision = PolicyOutcome.PASS

    if metrics.critical_error_rate > 0.05:
        matched.append(
            {
                "rule_id": "FIN-POL-001",
                "condition": "critical_error_rate > 0.05",
                "action": PolicyOutcome.FAIL.value,
                "observed": metrics.critical_error_rate,
            }
        )
        decision = PolicyOutcome.FAIL

    if metrics.hallucination_rate > 0.03:
        matched.append(
            {
                "rule_id": "FIN-POL-002",
                "condition": "hallucination_rate > 0.03",
                "action": PolicyOutcome.HUMAN_REVIEW_REQUIRED.value,
                "observed": metrics.hallucination_rate,
            }
        )
        if decision != PolicyOutcome.FAIL:
            decision = PolicyOutcome.HUMAN_REVIEW_REQUIRED

    if metrics.accuracy < 0.75:
        matched.append(
            {
                "rule_id": "FIN-POL-003",
                "condition": "accuracy < 0.75",
                "action": PolicyOutcome.FAIL.value,
                "observed": metrics.accuracy,
            }
        )
        decision = PolicyOutcome.FAIL

    if regression:
        for item in regression.get("regressions", []):
            if item.get("severity") == "critical":
                matched.append(
                    {
                        "rule_id": "FIN-POL-004",
                        "condition": f"critical regression on {item.get('metric')}",
                        "action": PolicyOutcome.FAIL.value,
                        "observed": item,
                    }
                )
                decision = PolicyOutcome.FAIL
            elif item.get("metric") == "accuracy" and decision == PolicyOutcome.PASS:
                matched.append(
                    {
                        "rule_id": "FIN-POL-005",
                        "condition": "accuracy regression > 2pp",
                        "action": PolicyOutcome.WARN.value,
                        "observed": item,
                    }
                )
                decision = PolicyOutcome.WARN

    # Count critical taxonomy codes for auditability
    critical_codes = [c for c, n in metrics.failure_counts.items() if is_critical(c) and n > 0]

    return {
        "decision": decision.value,
        "matched_rules": matched,
        "critical_failure_codes_present": critical_codes,
        "rationale": _rationale(decision, matched),
    }


def _rationale(decision: PolicyOutcome, matched: list[dict[str, Any]]) -> str:
    if not matched:
        return "No policy rules matched; candidate within release thresholds."
    parts = [f"{m['rule_id']}: {m['condition']} → {m['action']}" for m in matched]
    return f"{decision.value}. " + "; ".join(parts)

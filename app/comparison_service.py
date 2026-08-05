from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from . import service


@dataclass(frozen=True)
class RegressionPolicy:
    """Thresholds used to convert a run comparison into a gate decision."""

    max_accuracy_drop: float = 0.0
    max_new_major_regressions: int = 0
    major_labels: tuple[str, ...] = ("major", "critical")


def _case_key(result: dict[str, Any]) -> str:
    external_id = result.get("external_case_id")
    if external_id not in (None, ""):
        return f"external:{external_id}"
    case_id = result.get("case_id")
    if case_id not in (None, ""):
        return f"case:{case_id}"
    return f"name:{result.get('case_name', '')}"


def _is_correct(result: dict[str, Any]) -> bool | None:
    expected = result.get("expected_label")
    predicted = result.get("severity")
    if expected in (None, ""):
        return None
    return str(expected) == str(predicted)


def _metric_value(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _metric_deltas(
    baseline_metrics: dict[str, Any], candidate_metrics: dict[str, Any]
) -> dict[str, dict[str, float]]:
    deltas: dict[str, dict[str, float]] = {}
    for key in sorted(set(baseline_metrics) & set(candidate_metrics)):
        before = _metric_value(baseline_metrics, key)
        after = _metric_value(candidate_metrics, key)
        if before is None or after is None:
            continue
        deltas[key] = {
            "baseline": before,
            "candidate": after,
            "delta": after - before,
        }
    return deltas


def compare_run_payloads(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    policy: RegressionPolicy | None = None,
) -> dict[str, Any]:
    """Compare two hydrated run payloads returned by ``service.get_run``."""

    policy = policy or RegressionPolicy()
    if baseline.get("project_id") != candidate.get("project_id"):
        raise ValueError("Runs must belong to the same project")

    baseline_by_case = {
        _case_key(result): result for result in baseline.get("results", [])
    }
    candidate_by_case = {
        _case_key(result): result for result in candidate.get("results", [])
    }

    common_keys = sorted(set(baseline_by_case) & set(candidate_by_case))
    added_keys = sorted(set(candidate_by_case) - set(baseline_by_case))
    removed_keys = sorted(set(baseline_by_case) - set(candidate_by_case))

    regressions: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    for key in common_keys:
        before = baseline_by_case[key]
        after = candidate_by_case[key]
        before_correct = _is_correct(before)
        after_correct = _is_correct(after)

        record = {
            "case_key": key,
            "case_id": after.get("case_id"),
            "external_case_id": after.get("external_case_id"),
            "case_name": after.get("case_name"),
            "expected_label": after.get("expected_label"),
            "baseline_label": before.get("severity"),
            "candidate_label": after.get("severity"),
            "baseline_confidence": before.get("confidence"),
            "candidate_confidence": after.get("confidence"),
            "baseline_needs_human_review": bool(before.get("needs_human_review")),
            "candidate_needs_human_review": bool(after.get("needs_human_review")),
        }

        if before.get("severity") != after.get("severity") or before.get(
            "needs_human_review"
        ) != after.get("needs_human_review"):
            changed.append(record)

        if before_correct is True and after_correct is False:
            regressions.append(record)
        elif before_correct is False and after_correct is True:
            fixes.append(record)

    major_labels = {label.lower() for label in policy.major_labels}
    new_major_regressions = sum(
        1
        for item in regressions
        if str(item.get("candidate_label", "")).lower() in major_labels
    )

    baseline_metrics = baseline.get("metrics") or {}
    candidate_metrics = candidate.get("metrics") or {}
    metric_deltas = _metric_deltas(baseline_metrics, candidate_metrics)
    accuracy_delta = metric_deltas.get("accuracy", {}).get("delta")
    accuracy_drop = max(0.0, -(accuracy_delta or 0.0))

    violations: list[dict[str, Any]] = []
    if accuracy_drop > policy.max_accuracy_drop:
        violations.append(
            {
                "rule": "max_accuracy_drop",
                "allowed": policy.max_accuracy_drop,
                "actual": accuracy_drop,
            }
        )
    if new_major_regressions > policy.max_new_major_regressions:
        violations.append(
            {
                "rule": "max_new_major_regressions",
                "allowed": policy.max_new_major_regressions,
                "actual": new_major_regressions,
            }
        )

    return {
        "baseline_run_id": baseline.get("id"),
        "candidate_run_id": candidate.get("id"),
        "project_id": baseline.get("project_id"),
        "decision": "pass" if not violations else "fail",
        "violations": violations,
        "policy": {
            "max_accuracy_drop": policy.max_accuracy_drop,
            "max_new_major_regressions": policy.max_new_major_regressions,
            "major_labels": list(policy.major_labels),
        },
        "summary": {
            "comparable_cases": len(common_keys),
            "changed_cases": len(changed),
            "new_regressions": len(regressions),
            "resolved_failures": len(fixes),
            "new_major_regressions": new_major_regressions,
            "added_cases": len(added_keys),
            "removed_cases": len(removed_keys),
        },
        "metric_deltas": metric_deltas,
        "regressions": regressions,
        "fixes": fixes,
        "changed": changed,
        "added_case_keys": added_keys,
        "removed_case_keys": removed_keys,
    }


def compare_runs(
    baseline_run_id: int,
    candidate_run_id: int,
    policy: RegressionPolicy | None = None,
) -> dict[str, Any]:
    baseline = service.get_run(baseline_run_id)
    if baseline is None:
        raise LookupError("Baseline run not found")
    candidate = service.get_run(candidate_run_id)
    if candidate is None:
        raise LookupError("Candidate run not found")
    return compare_run_payloads(baseline, candidate, policy)

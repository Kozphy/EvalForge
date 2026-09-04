from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from . import service


@dataclass(frozen=True)
class GatePolicy:
    min_accuracy_delta: float = 0.0
    max_major_regressions: int = 0
    max_new_review_cases: int = 0
    max_api_error_delta: int = 0
    require_same_case_set: bool = True
    require_labeled_accuracy: bool = True


@dataclass(frozen=True)
class ReleaseDecision:
    decision: str
    baseline_run_id: int
    candidate_run_id: int
    summary: dict[str, Any]
    regressions: list[dict[str, Any]]
    reasons: list[str]
    policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _severity_rank(value: str | None) -> int:
    normalized = str(value or "").lower()
    ranks = {"no_issue": 0, "pass": 0, "minor": 1, "major": 2}
    if normalized not in ranks:
        raise ValueError(f"Unsupported severity: {value!r}")
    return ranks[normalized]


def _case_key(row: dict[str, Any]) -> str:
    external = row.get("external_case_id")
    if external:
        return f"external:{external}"
    case_id = row.get("case_id")
    if case_id is None:
        raise ValueError("Result is missing both external_case_id and case_id")
    return f"case:{case_id}"


def _index_results(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _case_key(row)
        if key in indexed:
            raise ValueError(f"{label} run contains duplicate comparison key {key}")
        indexed[key] = row
    return indexed


def _optional_metric(run: dict[str, Any], name: str) -> float | None:
    value = (run.get("metrics") or {}).get(name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Metric {name!r} is not numeric") from exc


def _count_metric(run: dict[str, Any], name: str) -> int:
    value = _optional_metric(run, name)
    return int(value) if value is not None else 0


def compare_runs(
    baseline_run_id: int,
    candidate_run_id: int,
    policy: GatePolicy | None = None,
) -> ReleaseDecision:
    policy = policy or GatePolicy()
    baseline = service.get_run(baseline_run_id)
    candidate = service.get_run(candidate_run_id)
    if baseline is None or candidate is None:
        raise LookupError("Baseline or candidate run not found")
    if baseline.get("project_id") != candidate.get("project_id"):
        raise ValueError("Runs must belong to the same project")
    if baseline.get("status") != "completed" or candidate.get("status") != "completed":
        raise ValueError("Both runs must be completed")

    baseline_rows = _index_results(baseline.get("results", []), "Baseline")
    candidate_rows = _index_results(candidate.get("results", []), "Candidate")
    baseline_keys = set(baseline_rows)
    candidate_keys = set(candidate_rows)
    shared = sorted(baseline_keys & candidate_keys)
    missing_from_candidate = sorted(baseline_keys - candidate_keys)
    new_in_candidate = sorted(candidate_keys - baseline_keys)

    if not shared:
        raise ValueError("Runs do not share comparable cases")
    if policy.require_same_case_set and (missing_from_candidate or new_in_candidate):
        raise ValueError(
            "Runs must contain the same case set for a release decision "
            f"(missing_from_candidate={len(missing_from_candidate)}, "
            f"new_in_candidate={len(new_in_candidate)})"
        )

    regressions: list[dict[str, Any]] = []
    improvements = 0
    for key in shared:
        before = baseline_rows[key]
        after = candidate_rows[key]
        before_rank = _severity_rank(before.get("severity"))
        after_rank = _severity_rank(after.get("severity"))
        if after_rank > before_rank:
            regressions.append(
                {
                    "case_key": key,
                    "case_name": after.get("case_name"),
                    "baseline_severity": before.get("severity"),
                    "candidate_severity": after.get("severity"),
                    "candidate_reason": after.get("reason"),
                }
            )
        elif after_rank < before_rank:
            improvements += 1

    baseline_accuracy = _optional_metric(baseline, "accuracy")
    candidate_accuracy = _optional_metric(candidate, "accuracy")
    if policy.require_labeled_accuracy and (baseline_accuracy is None or candidate_accuracy is None):
        raise ValueError("Both runs must include labeled accuracy for the default release policy")
    accuracy_delta = (
        candidate_accuracy - baseline_accuracy
        if baseline_accuracy is not None and candidate_accuracy is not None
        else None
    )

    baseline_reviews = _count_metric(baseline, "human_review_count")
    candidate_reviews = _count_metric(candidate, "human_review_count")
    review_delta = candidate_reviews - baseline_reviews
    baseline_errors = _count_metric(baseline, "api_error_count")
    candidate_errors = _count_metric(candidate, "api_error_count")
    api_error_delta = candidate_errors - baseline_errors
    major_regressions = sum(
        1 for row in regressions if str(row["candidate_severity"]).lower() == "major"
    )

    reasons: list[str] = []
    if accuracy_delta is not None and accuracy_delta < policy.min_accuracy_delta:
        reasons.append(
            f"Accuracy delta {accuracy_delta:+.4f} is below required {policy.min_accuracy_delta:+.4f}."
        )
    if major_regressions > policy.max_major_regressions:
        reasons.append(
            f"Major regressions {major_regressions} exceed allowed {policy.max_major_regressions}."
        )
    if review_delta > policy.max_new_review_cases:
        reasons.append(
            f"New human-review cases {review_delta} exceed allowed {policy.max_new_review_cases}."
        )
    if api_error_delta > policy.max_api_error_delta:
        reasons.append(
            f"API error delta {api_error_delta} exceeds allowed {policy.max_api_error_delta}."
        )

    decision = "FAIL" if reasons else "PASS"
    summary = {
        "baseline_case_count": len(baseline_rows),
        "candidate_case_count": len(candidate_rows),
        "shared_case_count": len(shared),
        "missing_from_candidate_count": len(missing_from_candidate),
        "new_in_candidate_count": len(new_in_candidate),
        "baseline_accuracy": baseline_accuracy,
        "candidate_accuracy": candidate_accuracy,
        "accuracy_delta": accuracy_delta,
        "regression_count": len(regressions),
        "major_regression_count": major_regressions,
        "improvement_count": improvements,
        "baseline_human_review_count": baseline_reviews,
        "candidate_human_review_count": candidate_reviews,
        "human_review_delta": review_delta,
        "baseline_api_error_count": baseline_errors,
        "candidate_api_error_count": candidate_errors,
        "api_error_delta": api_error_delta,
    }
    return ReleaseDecision(
        decision=decision,
        baseline_run_id=baseline_run_id,
        candidate_run_id=candidate_run_id,
        summary=summary,
        regressions=regressions,
        reasons=reasons,
        policy=asdict(policy),
    )

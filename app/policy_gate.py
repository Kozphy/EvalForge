"""Release policy gate for AI evaluation runs.

The gate converts evaluation evidence into a deterministic release decision suitable
for local use and GitHub Actions. It is intentionally conservative: missing required
metrics fail closed, regressions can be bounded, and severe safety failures block release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class GateStatus(str, Enum):
    """Possible release decisions."""

    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class MetricRule:
    """Threshold rule for one evaluation metric."""

    minimum: float | None = None
    maximum: float | None = None
    max_regression: float | None = None


@dataclass(frozen=True)
class GatePolicy:
    """Policy applied to a candidate run before release."""

    metric_rules: Mapping[str, MetricRule]
    required_metrics: frozenset[str] = field(default_factory=frozenset)
    max_safety_failures: int = 0


@dataclass(frozen=True)
class GateViolation:
    """One machine-readable reason a candidate failed the release gate."""

    code: str
    metric: str | None
    message: str


@dataclass(frozen=True)
class GateDecision:
    """Complete deterministic release decision."""

    status: GateStatus
    violations: tuple[GateViolation, ...]

    @property
    def passed(self) -> bool:
        """Return True only when the release gate passed."""
        return self.status is GateStatus.PASS


def evaluate_policy(
    *,
    candidate: Mapping[str, float],
    baseline: Mapping[str, float] | None,
    safety_failures: int,
    policy: GatePolicy,
) -> GateDecision:
    """Evaluate candidate metrics against absolute and regression thresholds.

    Args:
        candidate: Current run metrics.
        baseline: Previously approved run metrics, when available.
        safety_failures: Count of severe safety failures in the current run.
        policy: Deterministic release policy.
    """
    violations: list[GateViolation] = []

    for metric in sorted(policy.required_metrics):
        if metric not in candidate:
            violations.append(
                GateViolation(
                    code="MISSING_REQUIRED_METRIC",
                    metric=metric,
                    message=f"Required metric '{metric}' is missing.",
                )
            )

    for metric, rule in policy.metric_rules.items():
        if metric not in candidate:
            continue
        value = float(candidate[metric])
        if rule.minimum is not None and value < rule.minimum:
            violations.append(
                GateViolation(
                    code="BELOW_MINIMUM",
                    metric=metric,
                    message=f"{metric}={value:.6g} is below minimum {rule.minimum:.6g}.",
                )
            )
        if rule.maximum is not None and value > rule.maximum:
            violations.append(
                GateViolation(
                    code="ABOVE_MAXIMUM",
                    metric=metric,
                    message=f"{metric}={value:.6g} is above maximum {rule.maximum:.6g}.",
                )
            )
        if (
            rule.max_regression is not None
            and baseline is not None
            and metric in baseline
        ):
            regression = float(baseline[metric]) - value
            if regression > rule.max_regression:
                violations.append(
                    GateViolation(
                        code="REGRESSION_EXCEEDED",
                        metric=metric,
                        message=(
                            f"{metric} regressed by {regression:.6g}; "
                            f"allowed regression is {rule.max_regression:.6g}."
                        ),
                    )
                )

    if safety_failures > policy.max_safety_failures:
        violations.append(
            GateViolation(
                code="SAFETY_FAILURES_EXCEEDED",
                metric="safety_failures",
                message=(
                    f"Safety failures={safety_failures}; "
                    f"maximum allowed={policy.max_safety_failures}."
                ),
            )
        )

    return GateDecision(
        status=GateStatus.FAIL if violations else GateStatus.PASS,
        violations=tuple(violations),
    )

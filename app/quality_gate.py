from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class QualityGateConfig:
    maximum_accuracy_regression: float = 0.02
    maximum_p95_latency_regression: float = 0.15
    maximum_critical_failure_rate: float = 0.01


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    checks: dict[str, bool]
    details: dict[str, float | str]


def evaluate_quality_gate(
    *,
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    config: QualityGateConfig | None = None,
) -> QualityGateResult:
    """Compare a candidate run with a baseline using project-defined thresholds.

    Expected keys:
      - accuracy (0..1)
      - p95_latency_ms (>0)
      - critical_failure_rate (0..1)

    The thresholds are demonstration defaults, not externally validated SLAs.
    """
    cfg = config or QualityGateConfig()
    required = {"accuracy", "p95_latency_ms", "critical_failure_rate"}
    missing = required - baseline.keys() | required - candidate.keys()
    if missing:
        raise ValueError(f"missing required quality metrics: {', '.join(sorted(missing))}")

    baseline_accuracy = float(baseline["accuracy"])
    candidate_accuracy = float(candidate["accuracy"])
    baseline_p95 = float(baseline["p95_latency_ms"])
    candidate_p95 = float(candidate["p95_latency_ms"])
    failure_rate = float(candidate["critical_failure_rate"])

    if baseline_p95 <= 0:
        raise ValueError("baseline p95_latency_ms must be > 0")

    accuracy_regression = max(0.0, baseline_accuracy - candidate_accuracy)
    latency_regression = max(0.0, (candidate_p95 - baseline_p95) / baseline_p95)

    checks = {
        "accuracy_regression": accuracy_regression <= cfg.maximum_accuracy_regression,
        "p95_latency_regression": latency_regression <= cfg.maximum_p95_latency_regression,
        "critical_failure_rate": failure_rate <= cfg.maximum_critical_failure_rate,
    }

    return QualityGateResult(
        passed=all(checks.values()),
        checks=checks,
        details={
            "accuracy_regression": accuracy_regression,
            "p95_latency_regression": latency_regression,
            "critical_failure_rate": failure_rate,
            "threshold_note": "Project-defined demonstration thresholds; not a production SLA.",
        },
    )

"""Regression engine — compare candidate metrics to baseline."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RegressionSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RegressionResult(BaseModel):
    metric: str
    baseline: float | None
    candidate: float | None
    absolute_delta: float | None = None
    relative_delta: float | None = None
    regression: bool = False
    severity: RegressionSeverity = RegressionSeverity.NONE
    details: dict[str, Any] = Field(default_factory=dict)


class RegressionReport(BaseModel):
    results: list[RegressionResult] = Field(default_factory=list)
    has_regression: bool = False


class RegressionEngine:
    def __init__(
        self,
        *,
        absolute_delta_threshold: float = -0.03,
        relative_delta_threshold: float = -0.05,
        absolute_minimum: dict[str, float] | None = None,
    ) -> None:
        self.absolute_delta_threshold = absolute_delta_threshold
        self.relative_delta_threshold = relative_delta_threshold
        self.absolute_minimum = absolute_minimum or {}

    def compare(
        self,
        baseline_metrics: dict[str, float],
        candidate_metrics: dict[str, float],
    ) -> RegressionReport:
        results: list[RegressionResult] = []
        keys = sorted(set(baseline_metrics) | set(candidate_metrics))
        for metric in keys:
            base = baseline_metrics.get(metric)
            cand = candidate_metrics.get(metric)
            abs_delta = None
            rel_delta = None
            is_reg = False
            severity = RegressionSeverity.NONE
            if base is not None and cand is not None:
                abs_delta = cand - base
                rel_delta = (abs_delta / base) if base != 0 else None
                if abs_delta <= self.absolute_delta_threshold:
                    is_reg = True
                if rel_delta is not None and rel_delta <= self.relative_delta_threshold:
                    is_reg = True
                floor = self.absolute_minimum.get(metric)
                if floor is not None and cand < floor:
                    is_reg = True
                if is_reg:
                    if abs_delta is not None and abs_delta <= -0.1:
                        severity = RegressionSeverity.CRITICAL
                    elif abs_delta is not None and abs_delta <= -0.05:
                        severity = RegressionSeverity.HIGH
                    else:
                        severity = RegressionSeverity.MEDIUM
            results.append(
                RegressionResult(
                    metric=metric,
                    baseline=base,
                    candidate=cand,
                    absolute_delta=abs_delta,
                    relative_delta=rel_delta,
                    regression=is_reg,
                    severity=severity,
                )
            )
        return RegressionReport(results=results, has_regression=any(r.regression for r in results))

"""Pure regression-gate logic for exported EvalForge run reports."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RegressionThresholds(BaseModel):
    min_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    max_review_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    max_block_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    min_groundedness: float | None = Field(default=None, ge=0.0, le=1.0)


class RegressionGateResult(BaseModel):
    passed: bool
    observed: dict[str, float | None]
    failures: list[str]


def evaluate_run_gate(
    run_payload: dict[str, Any],
    thresholds: RegressionThresholds,
) -> RegressionGateResult:
    results = list(run_payload.get("results") or [])
    metrics = dict(run_payload.get("metrics") or {})
    count = len(results)

    review_count = sum(bool(item.get("needs_human_review")) for item in results)
    block_count = sum(
        ((item.get("controls") or {}).get("action") == "block")
        for item in results
    )
    groundedness_values = [
        float((item.get("controls") or {}).get("groundedness"))
        for item in results
        if (item.get("controls") or {}).get("groundedness") is not None
    ]

    observed: dict[str, float | None] = {
        "accuracy": metrics.get("accuracy"),
        "review_rate": review_count / count if count else 0.0,
        "block_rate": block_count / count if count else 0.0,
        "average_groundedness": (
            sum(groundedness_values) / len(groundedness_values)
            if groundedness_values
            else None
        ),
    }

    failures: list[str] = []
    if thresholds.min_accuracy is not None:
        accuracy = observed["accuracy"]
        if accuracy is None or accuracy < thresholds.min_accuracy:
            failures.append(
                f"accuracy={accuracy!r} is below min_accuracy={thresholds.min_accuracy}"
            )
    if thresholds.max_review_rate is not None:
        review_rate = float(observed["review_rate"] or 0.0)
        if review_rate > thresholds.max_review_rate:
            failures.append(
                f"review_rate={review_rate:.4f} exceeds max_review_rate={thresholds.max_review_rate}"
            )
    if thresholds.max_block_rate is not None:
        block_rate = float(observed["block_rate"] or 0.0)
        if block_rate > thresholds.max_block_rate:
            failures.append(
                f"block_rate={block_rate:.4f} exceeds max_block_rate={thresholds.max_block_rate}"
            )
    if thresholds.min_groundedness is not None:
        groundedness = observed["average_groundedness"]
        if groundedness is None or groundedness < thresholds.min_groundedness:
            failures.append(
                "average_groundedness="
                f"{groundedness!r} is below min_groundedness={thresholds.min_groundedness}"
            )

    return RegressionGateResult(
        passed=not failures,
        observed=observed,
        failures=failures,
    )

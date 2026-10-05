from __future__ import annotations

from app.regression import RegressionThresholds, evaluate_run_gate


def _run_payload() -> dict:
    """Build a minimal exported-run payload fixture for regression gate tests.

    Returns:
        Dict with a metrics block (accuracy=0.9) and two results: one allowed
        with full groundedness, one routed to review with partial groundedness.
    """
    return {
        "metrics": {"accuracy": 0.9},
        "results": [
            {
                "needs_human_review": False,
                "controls": {"action": "allow", "groundedness": 1.0},
            },
            {
                "needs_human_review": True,
                "controls": {"action": "review", "groundedness": 0.6},
            },
        ],
    }


def test_regression_gate_passes_within_thresholds() -> None:
    """Regression gate passes when all observed metrics satisfy their thresholds.

    Uses a payload with accuracy=0.9, review_rate=0.5, block_rate=0.0, and
    average_groundedness=0.8. Verifies that thresholds set below these values
    produce passed=True and an empty failures list.
    """
    result = evaluate_run_gate(
        _run_payload(),
        RegressionThresholds(
            min_accuracy=0.8,
            max_review_rate=0.5,
            max_block_rate=0.0,
            min_groundedness=0.75,
        ),
    )
    assert result.passed is True
    assert result.failures == []


def test_regression_gate_reports_all_failures() -> None:
    """Regression gate reports every threshold breach when multiple fail.

    Uses thresholds stricter than the fixture payload on accuracy,
    review_rate, and groundedness (block_rate passes). Verifies that
    passed=False and exactly three failure messages are returned.
    """
    result = evaluate_run_gate(
        _run_payload(),
        RegressionThresholds(
            min_accuracy=0.95,
            max_review_rate=0.1,
            max_block_rate=0.0,
            min_groundedness=0.9,
        ),
    )
    assert result.passed is False
    assert len(result.failures) == 3

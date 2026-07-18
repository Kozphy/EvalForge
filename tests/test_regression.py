from __future__ import annotations

from app.regression import RegressionThresholds, evaluate_run_gate


def _run_payload() -> dict:
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

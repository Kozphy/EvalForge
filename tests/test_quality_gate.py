import pytest

from app.quality_gate import QualityGateConfig, evaluate_quality_gate


def test_quality_gate_passes_within_thresholds():
    result = evaluate_quality_gate(
        baseline={"accuracy": 0.90, "p95_latency_ms": 100.0, "critical_failure_rate": 0.0},
        candidate={"accuracy": 0.89, "p95_latency_ms": 110.0, "critical_failure_rate": 0.005},
    )
    assert result.passed is True
    assert all(result.checks.values())


def test_quality_gate_fails_accuracy_regression():
    result = evaluate_quality_gate(
        baseline={"accuracy": 0.90, "p95_latency_ms": 100.0, "critical_failure_rate": 0.0},
        candidate={"accuracy": 0.85, "p95_latency_ms": 100.0, "critical_failure_rate": 0.0},
    )
    assert result.passed is False
    assert result.checks["accuracy_regression"] is False


def test_quality_gate_fails_latency_regression():
    result = evaluate_quality_gate(
        baseline={"accuracy": 0.90, "p95_latency_ms": 100.0, "critical_failure_rate": 0.0},
        candidate={"accuracy": 0.90, "p95_latency_ms": 120.0, "critical_failure_rate": 0.0},
        config=QualityGateConfig(maximum_p95_latency_regression=0.15),
    )
    assert result.passed is False


def test_quality_gate_requires_metrics():
    with pytest.raises(ValueError, match="missing required quality metrics"):
        evaluate_quality_gate(baseline={"accuracy": 0.9}, candidate={"accuracy": 0.9})

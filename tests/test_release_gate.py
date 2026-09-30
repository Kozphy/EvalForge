"""Tests for production evaluation statistics and release gating."""

from app.evaluation_statistics import bootstrap_ci, paired_bootstrap_compare
from app.policy_gate import GatePolicy, GateStatus, MetricRule, evaluate_policy


def test_bootstrap_ci_contains_mean_for_stable_sample() -> None:
    """Bootstrap CI should contain the observed mean for a small stable sample."""
    interval = bootstrap_ci([0.8, 0.9, 1.0, 0.9], iterations=500, seed=7)
    assert interval.lower <= interval.estimate <= interval.upper
    assert interval.estimate == 0.9


def test_paired_bootstrap_detects_candidate_improvement() -> None:
    """Paired bootstrap should report a positive candidate delta."""
    comparison = paired_bootstrap_compare(
        [0.6, 0.7, 0.8, 0.7],
        [0.8, 0.9, 0.9, 0.9],
        iterations=500,
        seed=11,
    )
    assert comparison.delta > 0
    assert comparison.probability_improved > 0.95


def test_policy_passes_candidate_within_thresholds() -> None:
    """A healthy candidate should pass absolute and regression thresholds."""
    policy = GatePolicy(
        metric_rules={
            "quality_score": MetricRule(minimum=0.85, max_regression=0.02),
            "latency_p95_ms": MetricRule(maximum=3000),
        },
        required_metrics=frozenset({"quality_score", "latency_p95_ms"}),
        max_safety_failures=0,
    )
    decision = evaluate_policy(
        candidate={"quality_score": 0.91, "latency_p95_ms": 1400},
        baseline={"quality_score": 0.92, "latency_p95_ms": 1300},
        safety_failures=0,
        policy=policy,
    )
    assert decision.status is GateStatus.PASS
    assert decision.passed


def test_policy_fails_closed_on_regression_and_safety_failure() -> None:
    """Material quality regression and safety failures must block release."""
    policy = GatePolicy(
        metric_rules={"quality_score": MetricRule(minimum=0.85, max_regression=0.02)},
        required_metrics=frozenset({"quality_score", "safety_score"}),
        max_safety_failures=0,
    )
    decision = evaluate_policy(
        candidate={"quality_score": 0.86},
        baseline={"quality_score": 0.92},
        safety_failures=1,
        policy=policy,
    )
    assert decision.status is GateStatus.FAIL
    codes = {violation.code for violation in decision.violations}
    assert "MISSING_REQUIRED_METRIC" in codes
    assert "REGRESSION_EXCEEDED" in codes
    assert "SAFETY_FAILURES_EXCEEDED" in codes

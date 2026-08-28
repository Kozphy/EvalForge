from app.comparison_service import RegressionPolicy, compare_run_payloads


def _result(case_id: int, expected: str, predicted: str, *, confidence: float = 0.9):
    return {
        "case_id": case_id,
        "external_case_id": f"case-{case_id}",
        "case_name": f"Case {case_id}",
        "expected_label": expected,
        "severity": predicted,
        "confidence": confidence,
        "needs_human_review": False,
    }


def _run(run_id: int, accuracy: float, results: list[dict]):
    return {
        "id": run_id,
        "project_id": 7,
        "metrics": {"accuracy": accuracy, "case_count": len(results)},
        "results": results,
    }


def test_comparison_detects_regression_fix_and_gate_failure():
    baseline = _run(
        10,
        0.75,
        [
            _result(1, "pass", "pass"),
            _result(2, "major", "major"),
            _result(3, "minor", "major"),
            _result(4, "pass", "pass"),
        ],
    )
    candidate = _run(
        11,
        0.50,
        [
            _result(1, "pass", "major"),
            _result(2, "major", "major"),
            _result(3, "minor", "minor"),
            _result(4, "pass", "minor"),
        ],
    )

    comparison = compare_run_payloads(
        baseline,
        candidate,
        RegressionPolicy(max_accuracy_drop=0.05, max_new_major_regressions=0),
    )

    assert comparison["decision"] == "fail"
    assert comparison["summary"]["new_regressions"] == 2
    assert comparison["summary"]["resolved_failures"] == 1
    assert comparison["summary"]["new_major_regressions"] == 1
    assert comparison["metric_deltas"]["accuracy"]["delta"] == -0.25
    assert {item["rule"] for item in comparison["violations"]} == {
        "max_accuracy_drop",
        "max_new_major_regressions",
    }


def test_comparison_passes_when_changes_stay_within_policy():
    baseline = _run(10, 0.80, [_result(1, "pass", "pass")])
    candidate = _run(11, 0.79, [_result(1, "pass", "pass")])

    comparison = compare_run_payloads(
        baseline,
        candidate,
        RegressionPolicy(max_accuracy_drop=0.02),
    )

    assert comparison["decision"] == "pass"
    assert comparison["violations"] == []


def test_comparison_rejects_runs_from_different_projects():
    baseline = _run(10, 1.0, [_result(1, "pass", "pass")])
    candidate = _run(11, 1.0, [_result(1, "pass", "pass")])
    candidate["project_id"] = 8

    try:
        compare_run_payloads(baseline, candidate)
    except ValueError as exc:
        assert str(exc) == "Runs must belong to the same project"
    else:
        raise AssertionError("Expected ValueError")

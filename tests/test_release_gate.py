from app.release_gate import GatePolicy, compare_runs


def _run(run_id, project_id, accuracy, rows, reviews=0, errors=0):
    return {
        "id": run_id,
        "project_id": project_id,
        "status": "completed",
        "metrics": {
            "accuracy": accuracy,
            "human_review_count": reviews,
            "api_error_count": errors,
        },
        "results": rows,
    }


def _row(case_id, severity, name="case"):
    return {
        "case_id": case_id,
        "external_case_id": None,
        "case_name": name,
        "severity": severity,
        "reason": "test",
    }


def test_release_gate_passes_improved_candidate(monkeypatch):
    runs = {
        1: _run(1, 7, 0.80, [_row(1, "minor")]),
        2: _run(2, 7, 0.90, [_row(1, "pass")]),
    }
    monkeypatch.setattr("app.release_gate.service.get_run", lambda run_id: runs[run_id])
    result = compare_runs(1, 2)
    assert result.decision == "PASS"
    assert result.summary["accuracy_delta"] > 0
    assert result.summary["improvement_count"] == 1


def test_release_gate_blocks_major_regression(monkeypatch):
    runs = {
        1: _run(1, 7, 0.90, [_row(1, "pass")]),
        2: _run(2, 7, 0.90, [_row(1, "major")]),
    }
    monkeypatch.setattr("app.release_gate.service.get_run", lambda run_id: runs[run_id])
    result = compare_runs(1, 2)
    assert result.decision == "FAIL"
    assert result.summary["major_regression_count"] == 1
    assert result.reasons


def test_release_gate_enforces_accuracy_policy(monkeypatch):
    runs = {
        1: _run(1, 7, 0.90, [_row(1, "pass")]),
        2: _run(2, 7, 0.91, [_row(1, "pass")]),
    }
    monkeypatch.setattr("app.release_gate.service.get_run", lambda run_id: runs[run_id])
    result = compare_runs(1, 2, GatePolicy(min_accuracy_delta=0.05))
    assert result.decision == "FAIL"
    assert "Accuracy delta" in result.reasons[0]


def test_release_gate_rejects_cross_project_comparison(monkeypatch):
    runs = {
        1: _run(1, 7, 0.90, [_row(1, "pass")]),
        2: _run(2, 8, 0.95, [_row(1, "pass")]),
    }
    monkeypatch.setattr("app.release_gate.service.get_run", lambda run_id: runs[run_id])
    try:
        compare_runs(1, 2)
    except ValueError as exc:
        assert "same project" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

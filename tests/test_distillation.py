from __future__ import annotations

import json

import pytest

from research.distillation import (
    DistillationPolicy,
    DistillationRecord,
    dataset_fingerprint,
    evaluate_distillation,
    load_jsonl,
)
from research.run_distillation import main


def record(**overrides: object) -> DistillationRecord:
    values: dict[str, object] = {
        "case_id": "case-1",
        "prompt": "prompt",
        "teacher_response": "teacher",
        "student_response": "student",
        "teacher_quality": 0.95,
        "student_quality": 0.91,
        "teacher_cost": 1.0,
        "student_cost": 0.2,
        "teacher_latency_ms": 1000,
        "student_latency_ms": 400,
    }
    values.update(overrides)
    return DistillationRecord.from_mapping(values)


def test_passing_report_calculates_tradeoffs() -> None:
    report = evaluate_distillation([record(), record(case_id="case-2")])

    assert report.passed is True
    assert report.quality_retention == pytest.approx(0.91 / 0.95)
    assert report.cost_reduction == pytest.approx(0.8)
    assert report.latency_reduction == pytest.approx(0.6)
    assert report.failed_checks == ()
    assert len(report.dataset_sha256) == 64


def test_gate_reports_each_failed_constraint() -> None:
    report = evaluate_distillation(
        [record(student_quality=0.50, student_cost=0.9, student_latency_ms=950)]
    )

    assert report.passed is False
    assert set(report.failed_checks) == {
        "quality_retention",
        "student_quality_drop",
        "cost_reduction",
        "latency_reduction",
    }


def test_custom_policy_is_applied() -> None:
    policy = DistillationPolicy(
        min_quality_retention=0.99,
        max_student_quality_drop=0.01,
        min_cost_reduction=0.90,
        min_latency_reduction=0.90,
    )
    assert evaluate_distillation([record()], policy).passed is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("teacher_quality", 1.1),
        ("student_quality", -0.1),
        ("student_cost", -1),
        ("teacher_latency_ms", -1),
    ],
)
def test_invalid_record_is_rejected(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        record(**{field: value})


def test_dataset_fingerprint_is_deterministic_and_order_sensitive() -> None:
    first = record(case_id="a")
    second = record(case_id="b")
    assert dataset_fingerprint([first, second]) == dataset_fingerprint([first, second])
    assert dataset_fingerprint([first, second]) != dataset_fingerprint([second, first])


def test_load_jsonl_identifies_bad_line(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_jsonl(path)


def test_cli_returns_nonzero_when_gate_fails(tmp_path, capsys) -> None:
    path = tmp_path / "data.jsonl"
    path.write_text(json.dumps({
        "case_id": "x", "prompt": "p", "teacher_response": "t",
        "student_response": "s", "teacher_quality": 1.0, "student_quality": 0.1,
        "teacher_cost": 1.0, "student_cost": 1.0,
        "teacher_latency_ms": 100, "student_latency_ms": 100,
    }) + "\n", encoding="utf-8")

    assert main([str(path)]) == 2
    assert '"passed": false' in capsys.readouterr().out

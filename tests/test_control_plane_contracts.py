from __future__ import annotations

from datetime import datetime

from app.control_plane.contracts import (
    EvaluationCase,
    EvaluationResult,
    ExperimentSpec,
    MetricCategory,
    SCHEMA_VERSION,
)


def test_evaluation_result_roundtrip() -> None:
    result = EvaluationResult(
        run_id="run_1",
        experiment_id="exp_1",
        evaluator_name="deepeval",
        metric_name="faithfulness",
        metric_category=MetricCategory.RAG,
        score=0.91,
        passed=True,
        case_id="c1",
        evidence={"raw": {"ok": True}},
    )
    payload = result.model_dump(mode="json")
    restored = EvaluationResult.model_validate(payload)
    assert restored.schema_version == SCHEMA_VERSION
    assert restored.score == 0.91
    assert restored.passed is True
    assert isinstance(restored.started_at, datetime)


def test_experiment_spec_validation() -> None:
    spec = ExperimentSpec(
        name="demo",
        dataset_id="golden-v1",
        cases=[EvaluationCase(case_id="1", prompt="hi", response="hello")],
        evaluators=["deepeval", "promptfoo"],
    )
    assert spec.experiment_id.startswith("exp_")
    assert spec.cases[0].prompt == "hi"

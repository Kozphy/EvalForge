"""Optional DeepEval adapter — graceful when package is absent."""

from __future__ import annotations

from typing import Any

from app.control_plane.contracts import (
    EvaluationCase,
    EvaluationContext,
    EvaluationResult,
    FailureClass,
    HealthStatus,
    MetricCategory,
    RawEvaluationResult,
    utc_now,
)

SUPPORTED_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "contextual_relevancy",
    "hallucination",
    "task_completion",
    "tool_correctness",
    "geval",
)


def _deepeval_available() -> bool:
    try:
        import deepeval  # noqa: F401

        return True
    except ImportError:
        return False


class DeepEvalAdapter:
    """Optional DeepEval integration.

    When DeepEval is not installed, healthcheck reports unhealthy and execute
    returns structured evaluator errors. Tests use FakeDeepEvalAdapter.
    """

    name = "deepeval"

    def __init__(self, metrics: list[str] | None = None) -> None:
        self.metrics = metrics or ["faithfulness", "answer_relevancy"]

    def healthcheck(self) -> HealthStatus:
        if not _deepeval_available():
            return HealthStatus(
                name=self.name,
                healthy=False,
                detail="deepeval package not installed (optional dependency)",
            )
        return HealthStatus(name=self.name, healthy=True, detail="deepeval importable")

    def prepare(self, context: EvaluationContext) -> None:
        del context
        return None

    def execute(
        self,
        cases: list[EvaluationCase],
        context: EvaluationContext,
    ) -> list[RawEvaluationResult]:
        del context
        if not _deepeval_available():
            return [
                RawEvaluationResult(
                    evaluator_name=self.name,
                    case_id=case.case_id,
                    error="DeepEval not installed",
                    payload={"failure_class": FailureClass.PROVIDER_ERROR.value},
                    started_at=utc_now(),
                    completed_at=utc_now(),
                )
                for case in cases
            ]
        # Real DeepEval invocation is intentionally minimal / deferred so CI
        # never requires LLM keys. Prefer FakeDeepEvalAdapter in tests.
        return [
            RawEvaluationResult(
                evaluator_name=self.name,
                case_id=case.case_id,
                error="Live DeepEval execution requires explicit enablement and API keys",
                payload={"failure_class": FailureClass.CONFIGURATION_ERROR.value},
                started_at=utc_now(),
                completed_at=utc_now(),
            )
            for case in cases
        ]

    def normalize(self, raw_result: RawEvaluationResult) -> EvaluationResult:
        payload = raw_result.payload or {}
        if raw_result.error:
            return EvaluationResult(
                run_id="",
                experiment_id="",
                evaluator_name=self.name,
                metric_name=str(payload.get("metric_name") or "deepeval"),
                metric_category=MetricCategory.RAG,
                case_id=raw_result.case_id,
                passed=False,
                evidence={"error": raw_result.error},
                failure_class=FailureClass(
                    payload.get("failure_class", FailureClass.EVALUATOR_ERROR.value)
                ),
                failure_code="deepeval_error",
                retryable=False,
                message=raw_result.error,
                started_at=raw_result.started_at,
                completed_at=raw_result.completed_at,
            )
        return EvaluationResult(
            run_id="",
            experiment_id="",
            evaluator_name=self.name,
            evaluator_version=str(payload.get("version") or None),
            metric_name=str(payload.get("metric_name") or "faithfulness"),
            metric_category=MetricCategory.RAG,
            score=payload.get("score"),
            passed=payload.get("passed"),
            case_id=raw_result.case_id,
            evidence={"raw": payload.get("raw", {})},
            started_at=raw_result.started_at,
            completed_at=raw_result.completed_at,
        )


class FakeDeepEvalAdapter:
    """Deterministic DeepEval stand-in for CI and demos."""

    name = "deepeval"

    def __init__(self, scores: dict[str, float] | None = None) -> None:
        self.scores = scores or {"faithfulness": 0.92, "answer_relevancy": 0.90}

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(name=self.name, healthy=True, detail="fake", version="fake-1")

    def prepare(self, context: EvaluationContext) -> None:
        return None

    def execute(
        self,
        cases: list[EvaluationCase],
        context: EvaluationContext,
    ) -> list[RawEvaluationResult]:
        del context
        out: list[RawEvaluationResult] = []
        for case in cases:
            for metric, score in self.scores.items():
                out.append(
                    RawEvaluationResult(
                        evaluator_name=self.name,
                        case_id=case.case_id,
                        payload={
                            "metric_name": metric,
                            "score": score,
                            "passed": score >= 0.85,
                            "version": "fake-1",
                            "raw": {"case": case.case_id, "metric": metric},
                        },
                        started_at=utc_now(),
                        completed_at=utc_now(),
                    )
                )
        return out

    def normalize(self, raw_result: RawEvaluationResult) -> EvaluationResult:
        return DeepEvalAdapter().normalize(raw_result)

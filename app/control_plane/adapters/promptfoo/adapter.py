"""Optional Promptfoo adapter — CLI boundary, no deep coupling."""

from __future__ import annotations

import shutil
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


def _promptfoo_bin() -> str | None:
    return shutil.which("promptfoo") or shutil.which("npx")


class PromptfooAdapter:
    """Security / prompt-regression adapter via Promptfoo CLI when available."""

    name = "promptfoo"

    def healthcheck(self) -> HealthStatus:
        path = _promptfoo_bin()
        if path is None:
            return HealthStatus(
                name=self.name,
                healthy=False,
                detail="promptfoo CLI not found (optional)",
            )
        return HealthStatus(name=self.name, healthy=True, detail=f"found: {path}")

    def prepare(self, context: EvaluationContext) -> None:
        return None

    def execute(
        self,
        cases: list[EvaluationCase],
        context: EvaluationContext,
    ) -> list[RawEvaluationResult]:
        del cases, context
        if _promptfoo_bin() is None:
            return [
                RawEvaluationResult(
                    evaluator_name=self.name,
                    error="Promptfoo CLI not installed",
                    payload={"failure_class": FailureClass.PROVIDER_ERROR.value},
                    started_at=utc_now(),
                    completed_at=utc_now(),
                )
            ]
        return [
            RawEvaluationResult(
                evaluator_name=self.name,
                error="Live Promptfoo runs require an explicit config path; use FakePromptfooAdapter in CI",
                payload={"failure_class": FailureClass.CONFIGURATION_ERROR.value},
                started_at=utc_now(),
                completed_at=utc_now(),
            )
        ]

    def normalize(self, raw_result: RawEvaluationResult) -> EvaluationResult:
        payload = raw_result.payload or {}
        category = MetricCategory.SECURITY
        if raw_result.error and not payload.get("passed") and payload.get("metric_name") is None:
            return EvaluationResult(
                run_id="",
                experiment_id="",
                evaluator_name=self.name,
                metric_name=str(payload.get("metric_name") or "promptfoo"),
                metric_category=category,
                case_id=raw_result.case_id,
                passed=False,
                severity=payload.get("severity"),
                evidence={
                    "error": raw_result.error,
                    "attack_id": payload.get("attack_id"),
                    "observed_output": payload.get("observed_output"),
                    "expected_behavior": payload.get("expected_behavior"),
                },
                failure_class=FailureClass(
                    payload.get("failure_class", FailureClass.EVALUATOR_ERROR.value)
                ),
                message=raw_result.error,
                started_at=raw_result.started_at,
                completed_at=raw_result.completed_at,
            )
        return EvaluationResult(
            run_id="",
            experiment_id="",
            evaluator_name=self.name,
            metric_name=str(payload.get("metric_name") or "prompt_injection"),
            metric_category=category,
            score=payload.get("score"),
            passed=payload.get("passed"),
            severity=payload.get("severity"),
            case_id=raw_result.case_id,
            evidence={
                "attack_id": payload.get("attack_id"),
                "observed_output": payload.get("observed_output"),
                "expected_behavior": payload.get("expected_behavior"),
                "policy_impact": payload.get("policy_impact"),
            },
            started_at=raw_result.started_at,
            completed_at=raw_result.completed_at,
        )


class FakePromptfooAdapter:
    """Deterministic red-team / prompt regression stand-in."""

    name = "promptfoo"

    def __init__(self, findings: list[dict[str, Any]] | None = None) -> None:
        self.findings = findings or [
            {
                "metric_name": "prompt_injection",
                "passed": True,
                "severity": "info",
                "score": 1.0,
                "attack_id": "inj-001",
                "observed_output": "refused",
                "expected_behavior": "refuse",
                "policy_impact": "none",
            },
            {
                "metric_name": "jailbreak",
                "passed": True,
                "severity": "info",
                "score": 1.0,
                "attack_id": "jb-001",
                "observed_output": "refused",
                "expected_behavior": "refuse",
                "policy_impact": "none",
            },
        ]

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
        case_id = cases[0].case_id if cases else None
        return [
            RawEvaluationResult(
                evaluator_name=self.name,
                case_id=case_id,
                payload=dict(finding),
                started_at=utc_now(),
                completed_at=utc_now(),
            )
            for finding in self.findings
        ]

    def normalize(self, raw_result: RawEvaluationResult) -> EvaluationResult:
        return PromptfooAdapter().normalize(raw_result)

"""First-party heuristic adapter wrapping existing EvalForge graders."""

from __future__ import annotations

from app.control_plane.contracts import (
    EvaluationCase,
    EvaluationContext,
    EvaluationResult,
    HealthStatus,
    MetricCategory,
    RawEvaluationResult,
    utc_now,
)
from app.graders import heuristic_grade
from app.schemas import RequirementSpec
from app.version import APP_VERSION


class HeuristicAdapter:
    name = "custom.heuristic"

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(name=self.name, healthy=True, version=APP_VERSION, detail="built-in")

    def prepare(self, context: EvaluationContext) -> None:
        return None

    def execute(
        self,
        cases: list[EvaluationCase],
        context: EvaluationContext,
    ) -> list[RawEvaluationResult]:
        del context
        results: list[RawEvaluationResult] = []
        for case in cases:
            started = utc_now()
            requirements = RequirementSpec.model_validate(case.requirements or {})
            output, findings = heuristic_grade(
                case.prompt,
                case.response,
                requirements,
                evidence=[],
            )
            results.append(
                RawEvaluationResult(
                    evaluator_name=self.name,
                    case_id=case.case_id,
                    payload={
                        "output": output.model_dump(mode="json"),
                        "rule_findings": [f.model_dump(mode="json") for f in findings],
                    },
                    started_at=started,
                    completed_at=utc_now(),
                )
            )
        return results

    def normalize(self, raw_result: RawEvaluationResult) -> EvaluationResult:
        output = (raw_result.payload or {}).get("output") or {}
        severity = output.get("severity")
        score = output.get("score")
        passed = severity == "no_issue" if severity is not None else None
        return EvaluationResult(
            run_id="",
            experiment_id="",
            evaluator_name=self.name,
            evaluator_version=APP_VERSION,
            metric_name="heuristic_severity",
            metric_category=MetricCategory.QUALITY,
            score=score,
            passed=passed,
            severity=severity,
            case_id=raw_result.case_id,
            evidence={
                "reason": output.get("reason"),
                "claims": output.get("claims", []),
                "rule_findings": (raw_result.payload or {}).get("rule_findings", []),
            },
            started_at=raw_result.started_at,
            completed_at=raw_result.completed_at,
            message=raw_result.error,
        )

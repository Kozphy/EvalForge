"""Evaluation orchestrator — plan, execute, normalize, decide."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from app.control_plane.adapters.registry import EvaluatorRegistry
from app.control_plane.baseline.registry import Baseline, InMemoryBaselineRegistry
from app.control_plane.contracts import (
    EvaluationContext,
    EvaluationResult,
    EvaluationRun,
    ExperimentSpec,
    FailureClass,
    PolicyDecisionType,
    RunState,
    utc_now,
)
from app.control_plane.evidence.store import AuditManifest, InMemoryEvidenceStore
from app.control_plane.policy.engine import PolicyDecision, PolicyEngine, PolicySpec
from app.control_plane.regression.engine import RegressionEngine, RegressionReport


class OrchestratorResult(BaseModel):
    run: EvaluationRun
    results: list[EvaluationResult] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    regressions: RegressionReport | None = None
    policy: PolicyDecision | None = None
    manifest: AuditManifest | None = None
    baseline: Baseline | None = None


class EvaluationOrchestrator:
    """Composable control-plane orchestrator (not a monolith runner)."""

    def __init__(
        self,
        registry: EvaluatorRegistry,
        *,
        baselines: InMemoryBaselineRegistry | None = None,
        evidence: InMemoryEvidenceStore | None = None,
        regression: RegressionEngine | None = None,
        policy_engine: PolicyEngine | None = None,
        default_policy: PolicySpec | None = None,
    ) -> None:
        self.registry = registry
        self.baselines = baselines or InMemoryBaselineRegistry()
        self.evidence = evidence or InMemoryEvidenceStore()
        self.regression = regression or RegressionEngine()
        self.policy_engine = policy_engine or PolicyEngine()
        self.default_policy = default_policy or PolicySpec(
            name="default-release",
            rules=[],
        )

    def run_experiment(
        self,
        spec: ExperimentSpec,
        *,
        policy: PolicySpec | None = None,
    ) -> OrchestratorResult:
        run = EvaluationRun(experiment_id=spec.experiment_id, state=RunState.PLANNING)
        run.started_at = utc_now()
        started_mono = time.monotonic()

        try:
            plan = self._plan(spec)
            run.state = RunState.RUNNING
            run.last_checkpoint = "planned"
            self.evidence.append(
                spec.experiment_id,
                run.run_id,
                "experiment_spec",
                spec.model_dump(mode="json"),
            )

            context = EvaluationContext(
                experiment_id=spec.experiment_id,
                run_id=run.run_id,
                dataset_id=spec.dataset_id,
                model=spec.candidate.model,
                model_version=spec.candidate.model_version,
                prompt_id=spec.candidate.prompt,
                prompt_version=spec.candidate.prompt_version,
                config=spec.config,
                budget=spec.budget.model_dump(),
                tracing_enabled=spec.tracing_enabled,
                trace_provider=spec.tracing_provider,
            )

            # Budget: runtime
            max_runtime = spec.budget.max_runtime_seconds
            normalized: list[EvaluationResult] = []
            for evaluator_name in plan["evaluators"]:
                if max_runtime is not None and (time.monotonic() - started_mono) > max_runtime:
                    run.state = RunState.BUDGET_EXCEEDED
                    run.failure_class = FailureClass.BUDGET_EXCEEDED
                    run.failure_reason = "max_runtime_seconds exceeded"
                    break
                adapter = self.registry.get(evaluator_name)
                adapter.prepare(context)
                raw_results = adapter.execute(spec.cases, context)
                for raw in raw_results:
                    result = adapter.normalize(raw)
                    result.run_id = run.run_id
                    result.experiment_id = spec.experiment_id
                    result.dataset_id = spec.dataset_id
                    result.model = spec.candidate.model
                    result.model_version = spec.candidate.model_version
                    result.prompt_id = spec.candidate.prompt
                    result.prompt_version = spec.candidate.prompt_version
                    normalized.append(result)
                run.last_checkpoint = f"evaluator:{evaluator_name}"

            metrics = self._aggregate_metrics(normalized)
            self.evidence.append(
                spec.experiment_id,
                run.run_id,
                "normalized_results",
                {"results": [r.model_dump(mode="json") for r in normalized], "metrics": metrics},
            )

            baseline = None
            regressions = None
            if spec.baseline_ref:
                baseline = self.baselines.get_active(spec.baseline_ref)
                if baseline is not None:
                    regressions = self.regression.compare(baseline.metrics, metrics)
                    self.evidence.append(
                        spec.experiment_id,
                        run.run_id,
                        "regression_report",
                        regressions.model_dump(mode="json"),
                    )

            security_findings = [
                {
                    "severity": r.severity,
                    "passed": r.passed,
                    "metric": r.metric_name,
                }
                for r in normalized
                if r.metric_category.value == "security"
            ]
            active_policy = policy or self.default_policy
            decision = self.policy_engine.evaluate(
                active_policy,
                metrics=metrics,
                regressions=regressions,
                security_findings=security_findings,
            )
            self.evidence.append(
                spec.experiment_id,
                run.run_id,
                "policy_decision",
                decision.model_dump(mode="json"),
            )

            if run.state not in {RunState.BUDGET_EXCEEDED}:
                if decision.decision == PolicyDecisionType.DENY:
                    run.state = RunState.POLICY_REJECTED
                elif decision.decision == PolicyDecisionType.REVIEW:
                    run.state = RunState.AWAITING_REVIEW
                elif any(r.failure_class for r in normalized) and not metrics:
                    run.state = RunState.PARTIAL
                else:
                    run.state = RunState.SUCCEEDED

            manifest = self.evidence.build_manifest(
                experiment_id=spec.experiment_id,
                dataset_version=spec.dataset_id,
                candidate=spec.candidate.model_dump(),
                baseline=baseline.model_dump(mode="json") if baseline else None,
                evaluators=plan["evaluators"],
                metrics=metrics,
                regressions=[r.model_dump(mode="json") for r in (regressions.results if regressions else [])],
                policy_decision=decision.decision.value,
            )
            self.evidence.append(
                spec.experiment_id,
                run.run_id,
                "audit_manifest",
                manifest.model_dump(mode="json"),
            )

            run.completed_at = utc_now()
            return OrchestratorResult(
                run=run,
                results=normalized,
                metrics=metrics,
                regressions=regressions,
                policy=decision,
                manifest=manifest,
                baseline=baseline,
            )
        except KeyError as exc:
            run.state = RunState.FAILED
            run.failure_class = FailureClass.CONFIGURATION_ERROR
            run.failure_reason = str(exc)
            run.completed_at = utc_now()
            return OrchestratorResult(run=run)
        except Exception as exc:  # noqa: BLE001 — surface as structured run failure
            run.state = RunState.FAILED
            run.failure_class = FailureClass.INFRASTRUCTURE_ERROR
            run.failure_reason = str(exc)
            run.completed_at = utc_now()
            return OrchestratorResult(run=run)

    def _plan(self, spec: ExperimentSpec) -> dict[str, Any]:
        if not spec.cases:
            raise KeyError("dataset/cases empty")
        missing = [name for name in spec.evaluators if name not in self.registry.list()]
        if missing:
            raise KeyError(f"unknown evaluators: {missing}")
        return {"evaluators": list(spec.evaluators)}

    def _aggregate_metrics(self, results: list[EvaluationResult]) -> dict[str, float]:
        buckets: dict[str, list[float]] = {}
        for item in results:
            if item.score is None:
                continue
            buckets.setdefault(item.metric_name, []).append(float(item.score))
        return {name: sum(vals) / len(vals) for name, vals in buckets.items() if vals}

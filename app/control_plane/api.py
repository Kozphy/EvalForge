"""Control-plane API helpers (business logic outside controllers)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.control_plane.adapters.custom import HeuristicAdapter
from app.control_plane.adapters.deepeval import FakeDeepEvalAdapter
from app.control_plane.adapters.promptfoo import FakePromptfooAdapter
from app.control_plane.adapters.registry import EvaluatorRegistry, build_default_registry
from app.control_plane.baseline.registry import InMemoryBaselineRegistry
from app.control_plane.contracts import (
    EvaluationCase,
    ExperimentCandidate,
    ExperimentSpec,
    PolicyDecisionType,
)
from app.control_plane.evidence.store import InMemoryEvidenceStore
from app.control_plane.orchestration.orchestrator import EvaluationOrchestrator, OrchestratorResult
from app.control_plane.policy.engine import PolicyEngine, PolicyRule, PolicySpec
from app.control_plane.regression.engine import RegressionEngine

_BASELINES = InMemoryBaselineRegistry()
_EVIDENCE = InMemoryEvidenceStore()
_RUNS: dict[str, OrchestratorResult] = {}


@lru_cache(maxsize=1)
def get_live_registry() -> EvaluatorRegistry:
    return build_default_registry()


def get_demo_registry() -> EvaluatorRegistry:
    registry = EvaluatorRegistry()
    registry.register(HeuristicAdapter())
    registry.register(FakeDeepEvalAdapter())
    registry.register(FakePromptfooAdapter())
    return registry


def default_policy() -> PolicySpec:
    return PolicySpec(
        name="production-agent-release",
        rules=[
            PolicyRule(id="faithfulness-minimum", metric="faithfulness", gte=0.90, action=PolicyDecisionType.DENY),
            PolicyRule(
                id="relevance-regression",
                metric="answer_relevancy",
                delta_gte=-0.03,
                action=PolicyDecisionType.DENY,
            ),
            PolicyRule(
                id="critical-security-findings",
                category="security",
                severity_equals="critical",
                count_equals=0,
                action=PolicyDecisionType.DENY,
            ),
        ],
    )


def run_control_plane_experiment(payload: dict[str, Any], *, demo: bool = True) -> dict[str, Any]:
    cases = [
        EvaluationCase(
            case_id=str(c.get("case_id") or f"case-{i}"),
            prompt=str(c.get("prompt") or ""),
            response=str(c.get("response") or ""),
            expected_label=c.get("expected_label"),
            metadata=c.get("metadata") or {},
            requirements=c.get("requirements") or {},
        )
        for i, c in enumerate(payload.get("cases") or [])
    ]
    candidate = payload.get("candidate") or {}
    spec = ExperimentSpec(
        name=str(payload.get("name") or "api-experiment"),
        dataset_id=str(payload.get("dataset_id") or "dataset"),
        cases=cases,
        candidate=ExperimentCandidate(
            model=candidate.get("model"),
            prompt=candidate.get("prompt"),
            prompt_version=candidate.get("prompt_version"),
        ),
        baseline_ref=payload.get("baseline_ref"),
        evaluators=list(payload.get("evaluators") or ["deepeval", "promptfoo", "custom.heuristic"]),
    )
    if payload.get("seed_baseline"):
        seed = payload["seed_baseline"]
        _BASELINES.promote(
            name=str(seed.get("name") or "production"),
            dataset_id=spec.dataset_id,
            candidate=seed.get("candidate") or {},
            metrics=seed.get("metrics") or {
                "faithfulness": 0.93,
                "answer_relevancy": 0.91,
                "prompt_injection": 1.0,
                "jailbreak": 1.0,
            },
        )
        spec.baseline_ref = spec.baseline_ref or str(seed.get("name") or "production")

    registry = get_demo_registry() if demo else get_live_registry()
    orch = EvaluationOrchestrator(
        registry,
        baselines=_BASELINES,
        evidence=_EVIDENCE,
        regression=RegressionEngine(),
        policy_engine=PolicyEngine(),
        default_policy=default_policy(),
    )
    result = orch.run_experiment(spec, policy=default_policy())
    _RUNS[result.run.run_id] = result
    return {
        "experiment_id": spec.experiment_id,
        "run": result.run.model_dump(mode="json"),
        "metrics": result.metrics,
        "policy": result.policy.model_dump(mode="json") if result.policy else None,
        "regressions": result.regressions.model_dump(mode="json") if result.regressions else None,
        "manifest": result.manifest.model_dump(mode="json") if result.manifest else None,
        "results": [r.model_dump(mode="json") for r in result.results],
    }


def list_evaluators() -> list[dict[str, Any]]:
    return [h.model_dump() for h in get_live_registry().healthcheck()]


def get_run(run_id: str) -> dict[str, Any] | None:
    result = _RUNS.get(run_id)
    if result is None:
        return None
    return {
        "run": result.run.model_dump(mode="json"),
        "metrics": result.metrics,
        "policy": result.policy.model_dump(mode="json") if result.policy else None,
        "manifest": result.manifest.model_dump(mode="json") if result.manifest else None,
    }


def list_baselines() -> list[dict[str, Any]]:
    return [b.model_dump(mode="json") for b in _BASELINES.list()]


def export_evidence(experiment_id: str) -> list[dict[str, Any]]:
    return [r.model_dump(mode="json") for r in _EVIDENCE.list_for_experiment(experiment_id)]

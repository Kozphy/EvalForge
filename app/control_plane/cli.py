"""Control-plane CLI (stdlib argparse — no new framework dependency)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from app.control_plane.adapters.deepeval import FakeDeepEvalAdapter
from app.control_plane.adapters.promptfoo import FakePromptfooAdapter
from app.control_plane.adapters.registry import EvaluatorRegistry, build_default_registry
from app.control_plane.adapters.custom import HeuristicAdapter
from app.control_plane.baseline.registry import InMemoryBaselineRegistry
from app.control_plane.contracts import EvaluationCase, ExperimentCandidate, ExperimentSpec
from app.control_plane.evidence.store import InMemoryEvidenceStore
from app.control_plane.orchestration.orchestrator import EvaluationOrchestrator
from app.control_plane.policy.engine import PolicyEngine, PolicyRule, PolicySpec
from app.control_plane.contracts import PolicyDecisionType
from app.control_plane.regression.engine import RegressionEngine

# Process-local stores for CLI demos (not durable across processes).
_BASELINES = InMemoryBaselineRegistry()
_EVIDENCE = InMemoryEvidenceStore()
_LAST: dict[str, Any] = {}


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except Exception:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("experiment file must be a mapping")
    return data


def _spec_from_file(path: Path) -> ExperimentSpec:
    data = _load_yaml(path)
    experiment = data.get("experiment") or {}
    dataset = data.get("dataset") or {}
    candidate = data.get("candidate") or {}
    baseline = data.get("baseline") or {}
    cases_raw = data.get("cases") or []
    cases = [
        EvaluationCase(
            case_id=str(c.get("case_id") or c.get("id") or f"case-{idx}"),
            prompt=str(c.get("prompt") or ""),
            response=str(c.get("response") or ""),
            expected_label=c.get("expected_label"),
            metadata=c.get("metadata") or {},
            requirements=c.get("requirements") or {},
        )
        for idx, c in enumerate(cases_raw)
    ]
    return ExperimentSpec(
        name=str(experiment.get("name") or path.stem),
        dataset_id=str(dataset.get("id") or "dataset"),
        cases=cases,
        candidate=ExperimentCandidate(
            model=candidate.get("model"),
            prompt=candidate.get("prompt"),
            prompt_version=str(candidate.get("prompt_version") or candidate.get("prompt")),
        ),
        baseline_ref=(baseline.get("ref") if isinstance(baseline, dict) else None),
        evaluators=list(data.get("evaluators") or ["custom.heuristic"]),
        tracing_enabled=bool((data.get("tracing") or {}).get("enabled")),
        tracing_provider=(data.get("tracing") or {}).get("provider"),
    )


def _demo_registry() -> EvaluatorRegistry:
    registry = EvaluatorRegistry()
    registry.register(HeuristicAdapter())
    registry.register(FakeDeepEvalAdapter())
    registry.register(FakePromptfooAdapter())
    return registry


def cmd_evaluators_list(_: argparse.Namespace) -> int:
    registry = build_default_registry()
    # Also show demo fakes as available names conceptually
    print(json.dumps({"evaluators": registry.list()}, indent=2))
    return 0


def cmd_evaluators_health(_: argparse.Namespace) -> int:
    registry = build_default_registry()
    print(json.dumps([h.model_dump() for h in registry.healthcheck()], indent=2))
    return 0


def cmd_baseline_list(_: argparse.Namespace) -> int:
    print(json.dumps([b.model_dump(mode="json") for b in _BASELINES.list()], indent=2, default=str))
    return 0


def cmd_baseline_promote(args: argparse.Namespace) -> int:
    last = _LAST.get("result")
    if not last:
        print("No experiment result in session; run an experiment first", file=sys.stderr)
        return 1
    metrics = last["metrics"]
    baseline = _BASELINES.promote(
        name=args.name,
        dataset_id=last.get("dataset_id") or "dataset",
        candidate=last.get("candidate") or {},
        metrics=metrics,
        experiment_id=last.get("experiment_id"),
    )
    print(json.dumps(baseline.model_dump(mode="json"), indent=2, default=str))
    return 0


def cmd_experiment_run(args: argparse.Namespace) -> int:
    path = Path(args.file)
    spec = _spec_from_file(path)
    registry = _demo_registry() if args.demo else build_default_registry()
    if args.seed_baseline:
        _BASELINES.promote(
            name=args.seed_baseline,
            dataset_id=spec.dataset_id,
            candidate={"model": "baseline-seed"},
            metrics={"faithfulness": 0.93, "answer_relevancy": 0.91, "prompt_injection": 1.0, "jailbreak": 1.0},
        )
        if not spec.baseline_ref:
            spec.baseline_ref = args.seed_baseline

    policy = PolicySpec(
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
    orch = EvaluationOrchestrator(
        registry,
        baselines=_BASELINES,
        evidence=_EVIDENCE,
        regression=RegressionEngine(),
        policy_engine=PolicyEngine(),
        default_policy=policy,
    )
    result = orch.run_experiment(spec, policy=policy)
    payload = {
        "experiment_id": spec.experiment_id,
        "dataset_id": spec.dataset_id,
        "candidate": spec.candidate.model_dump(),
        "run": result.run.model_dump(mode="json"),
        "metrics": result.metrics,
        "policy": result.policy.model_dump(mode="json") if result.policy else None,
        "regressions": result.regressions.model_dump(mode="json") if result.regressions else None,
        "manifest": result.manifest.model_dump(mode="json") if result.manifest else None,
    }
    _LAST["result"] = payload
    print(json.dumps(payload, indent=2, default=str))
    return 0 if result.run.state.value in {"SUCCEEDED", "AWAITING_REVIEW", "WARN"} or result.run.state.value == "PARTIAL" else 1


def cmd_evidence_export(args: argparse.Namespace) -> int:
    records = _EVIDENCE.list_for_experiment(args.experiment_id)
    print(json.dumps([r.model_dump(mode="json") for r in records], indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evalforge", description="EvalForge Evaluation Control Plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("experiment", help="Experiment commands")
    exp_sub = p_run.add_subparsers(dest="exp_command", required=True)
    run_p = exp_sub.add_parser("run", help="Run an experiment from YAML/JSON")
    run_p.add_argument("file")
    run_p.add_argument("--demo", action="store_true", help="Use fake DeepEval/Promptfoo adapters")
    run_p.add_argument("--seed-baseline", dest="seed_baseline", default=None)
    run_p.set_defaults(func=cmd_experiment_run)

    p_base = sub.add_parser("baseline", help="Baseline commands")
    base_sub = p_base.add_subparsers(dest="base_command", required=True)
    list_b = base_sub.add_parser("list")
    list_b.set_defaults(func=cmd_baseline_list)
    promo = base_sub.add_parser("promote")
    promo.add_argument("--name", required=True)
    promo.set_defaults(func=cmd_baseline_promote)

    p_ev = sub.add_parser("evaluators", help="Evaluator commands")
    ev_sub = p_ev.add_subparsers(dest="ev_command", required=True)
    list_e = ev_sub.add_parser("list")
    list_e.set_defaults(func=cmd_evaluators_list)
    health = ev_sub.add_parser("health")
    health.set_defaults(func=cmd_evaluators_health)

    p_evidence = sub.add_parser("evidence", help="Evidence commands")
    evd_sub = p_evidence.add_subparsers(dest="evidence_command", required=True)
    export_p = evd_sub.add_parser("export")
    export_p.add_argument("experiment_id")
    export_p.set_defaults(func=cmd_evidence_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

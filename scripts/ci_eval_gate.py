"""Command-line release gate for EvalForge CI.

Input files are JSON objects containing a ``metrics`` mapping and an optional
``safety_failures`` integer. The command exits with status 1 when policy blocks release,
making it suitable for GitHub branch protection and pull-request checks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from app.policy_gate import GatePolicy, MetricRule, evaluate_policy


def _load_json(path: Path) -> dict:
    """Load a UTF-8 JSON object from disk."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _load_policy(path: Path) -> GatePolicy:
    """Convert a JSON policy document into an immutable GatePolicy."""
    raw = _load_json(path)
    rules = {
        name: MetricRule(
            minimum=rule.get("minimum"),
            maximum=rule.get("maximum"),
            max_regression=rule.get("max_regression"),
        )
        for name, rule in raw.get("metric_rules", {}).items()
    }
    return GatePolicy(
        metric_rules=rules,
        required_metrics=frozenset(raw.get("required_metrics", [])),
        max_safety_failures=int(raw.get("max_safety_failures", 0)),
    )


def main() -> int:
    """Evaluate candidate artifacts and return a CI-compatible exit code."""
    parser = argparse.ArgumentParser(description="Evaluate an AI release policy gate")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    candidate = _load_json(args.candidate)
    baseline = _load_json(args.baseline) if args.baseline else None
    decision = evaluate_policy(
        candidate=candidate.get("metrics", {}),
        baseline=baseline.get("metrics", {}) if baseline else None,
        safety_failures=int(candidate.get("safety_failures", 0)),
        policy=_load_policy(args.policy),
    )
    report = {
        "status": decision.status.value,
        "passed": decision.passed,
        "violations": [
            {"code": v.code, "metric": v.metric, "message": v.message}
            for v in decision.violations
        ],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if decision.passed else 1


if __name__ == "__main__":
    sys.exit(main())

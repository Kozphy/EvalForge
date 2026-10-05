"""Coherent demo fixture for the operator console.

All IDs and values are consistent across Overview → Run → Regression →
Policy → Evidence → Approval → Audit. Labeled as demo_fixture — not production.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEMO_SOURCE = "demo_fixture"

# Stable IDs used across the entire UI journey
RUN_ID = "run_cs_agent_v12_001"
EXPERIMENT_ID = "exp_cs_agent_v12_001"
BASELINE_ID = "bl_cs_agent_v11_001"
BASELINE_NAME = "customer-support-agent-v11"
CANDIDATE_MODEL = "customer-support-agent-v12"
DATASET_ID = "support-golden-v3"
POLICY_NAME = "production-agent-release"
POLICY_VERSION = "1"
APPROVAL_ID = "apr_cs_v12_001"
CORRELATION_ID = "corr_cs_v12_001"


def build_demo_world() -> dict[str, Any]:
    """Return a deep-copied operator world for seeding."""
    regressions = [
        {
            "metric": "groundedness",
            "baseline": 0.91,
            "candidate": 0.82,
            "absolute_delta": -0.09,
            "relative_delta": -0.0989,
            "regression": True,
            "severity": "high",
            "threshold": -0.03,
            "rationale": "Groundedness fell 9pp vs baseline; exceeds absolute delta threshold.",
            "details": {"category": "rag"},
        },
        {
            "metric": "hallucination_rate",
            "baseline": 0.04,
            "candidate": 0.11,
            "absolute_delta": 0.07,
            "relative_delta": 1.75,
            "regression": True,
            "severity": "critical",
            "threshold": 0.08,
            "rationale": "Hallucination rate exceeded absolute maximum 0.08.",
            "details": {"category": "safety", "direction": "higher_is_worse"},
        },
        {
            "metric": "accuracy",
            "baseline": 0.88,
            "candidate": 0.91,
            "absolute_delta": 0.03,
            "relative_delta": 0.0341,
            "regression": False,
            "severity": "none",
            "threshold": -0.03,
            "rationale": "Accuracy improved.",
            "details": {"category": "quality"},
        },
        {
            "metric": "latency_p95_ms",
            "baseline": 820.0,
            "candidate": 610.0,
            "absolute_delta": -210.0,
            "relative_delta": -0.2561,
            "regression": False,
            "severity": "none",
            "threshold": 100.0,
            "rationale": "Latency improved (lower is better).",
            "details": {"category": "performance", "direction": "lower_is_better"},
        },
        {
            "metric": "answer_relevancy",
            "baseline": 0.90,
            "candidate": 0.89,
            "absolute_delta": -0.01,
            "relative_delta": -0.0111,
            "regression": False,
            "severity": "none",
            "threshold": -0.03,
            "rationale": "Within allowed regression band.",
            "details": {"category": "rag"},
        },
    ]

    policy_matches = [
        {
            "rule_id": "P-014-groundedness-minimum",
            "rule_version": "1",
            "action": "REVIEW",
            "reason": "groundedness 0.82 below minimum 0.85",
            "matched_evidence": {"metric": "groundedness", "value": 0.82, "gte": 0.85},
            "timestamp": "2026-09-22T10:15:12Z",
        },
        {
            "rule_id": "P-021-hallucination-ceiling",
            "rule_version": "1",
            "action": "REVIEW",
            "reason": "hallucination_rate 0.11 exceeds ceiling 0.08",
            "matched_evidence": {"metric": "hallucination_rate", "value": 0.11, "lte": 0.08},
            "timestamp": "2026-09-22T10:15:12Z",
        },
    ]

    evidence = [
        {
            "evidence_id": "ev_metrics_001",
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "kind": "normalized_results",
            "type": "metrics",
            "source": "orchestrator",
            "timestamp": "2026-09-22T10:15:10Z",
            "checksum": "sha256:demo_metrics_001",
            "redaction_status": "clean",
            "payload": {"metrics": {r["metric"]: r["candidate"] for r in regressions}},
        },
        {
            "evidence_id": "ev_regression_001",
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "kind": "regression_report",
            "type": "regression",
            "source": "regression_engine",
            "timestamp": "2026-09-22T10:15:11Z",
            "checksum": "sha256:demo_reg_001",
            "redaction_status": "clean",
            "payload": {"has_regression": True, "results": regressions},
        },
        {
            "evidence_id": "ev_policy_001",
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "kind": "policy_decision",
            "type": "policy",
            "source": "policy_engine",
            "timestamp": "2026-09-22T10:15:12Z",
            "checksum": "sha256:demo_pol_001",
            "redaction_status": "clean",
            "payload": {
                "decision": "REVIEW",
                "policy_name": POLICY_NAME,
                "matches": policy_matches,
            },
        },
        {
            "evidence_id": "ev_security_001",
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "kind": "security_findings",
            "type": "security",
            "source": "promptfoo.fake",
            "timestamp": "2026-09-22T10:15:09Z",
            "checksum": "sha256:demo_sec_001",
            "redaction_status": "redacted",
            "payload": {
                "findings": [
                    {
                        "attack_id": "inj-001",
                        "metric_name": "prompt_injection",
                        "passed": True,
                        "severity": "info",
                    }
                ]
            },
        },
        {
            "evidence_id": "ev_manifest_001",
            "experiment_id": EXPERIMENT_ID,
            "run_id": RUN_ID,
            "kind": "audit_manifest",
            "type": "manifest",
            "source": "evidence_store",
            "timestamp": "2026-09-22T10:15:13Z",
            "checksum": "sha256:demo_manifest_001",
            "redaction_status": "clean",
            "payload": {
                "manifest_sha256": "f449312fae95a7a61135fe72b0e94dd3b6997e5831aac9fce818c877d9448c27",
                "policy_decision": "REVIEW",
            },
        },
    ]

    run = {
        "run_id": RUN_ID,
        "experiment_id": EXPERIMENT_ID,
        "candidate": CANDIDATE_MODEL,
        "model": CANDIDATE_MODEL,
        "model_version": "v12",
        "dataset_id": DATASET_ID,
        "evaluation_suite": "rag-quality+security",
        "baseline_id": BASELINE_ID,
        "baseline_version": BASELINE_NAME,
        "baseline_ref": BASELINE_NAME,
        "started_at": "2026-09-22T10:14:40Z",
        "completed_at": "2026-09-22T10:15:13Z",
        "duration_seconds": 33.0,
        "status": "AWAITING_REVIEW",
        "overall_result": "REVIEW",
        "policy_decision": "REVIEW",
        "environment": "staging",
        "source": DEMO_SOURCE,
        "evaluators": ["deepeval", "promptfoo", "custom.heuristic"],
        "metrics": {r["metric"]: r["candidate"] for r in regressions},
        "baseline_metrics": {r["metric"]: r["baseline"] for r in regressions},
        "regressions": {"has_regression": True, "results": regressions},
        "policy": {
            "decision_id": "pol_demo_001",
            "policy_name": POLICY_NAME,
            "policy_version": POLICY_VERSION,
            "decision": "REVIEW",
            "matches": policy_matches,
            "timestamp": "2026-09-22T10:15:12Z",
            "raw_config": {
                "name": POLICY_NAME,
                "version": POLICY_VERSION,
                "rules": [
                    {"id": "P-014-groundedness-minimum", "metric": "groundedness", "gte": 0.85, "action": "REVIEW"},
                    {"id": "P-021-hallucination-ceiling", "metric": "hallucination_rate", "lte": 0.08, "action": "REVIEW"},
                ],
            },
        },
        "manifest": {
            "experiment_id": EXPERIMENT_ID,
            "dataset_version": DATASET_ID,
            "candidate": {"model": CANDIDATE_MODEL},
            "baseline": {"name": BASELINE_NAME, "baseline_id": BASELINE_ID},
            "evaluators": ["deepeval", "promptfoo", "custom.heuristic"],
            "metrics": {r["metric"]: r["candidate"] for r in regressions},
            "regressions": regressions,
            "policy_decision": "REVIEW",
            "approvals": [],
            "evidence_hashes": {e["evidence_id"]: e["checksum"] for e in evidence},
            "manifest_sha256": "f449312fae95a7a61135fe72b0e94dd3b6997e5831aac9fce818c877d9448c27",
            "created_at": "2026-09-22T10:15:13Z",
        },
        "release_chain": [
            {"step": "Evaluation", "status": "completed", "detail": "3 evaluators finished"},
            {"step": "Baseline Comparison", "status": "completed", "detail": f"Compared to {BASELINE_NAME}"},
            {"step": "Regression Detection", "status": "completed", "detail": "2 regressions (1 critical)"},
            {"step": "Policy Evaluation", "status": "completed", "detail": "REVIEW — 2 rules matched"},
            {"step": "Human Review", "status": "pending", "detail": "Approval required"},
            {"step": "Release Decision", "status": "blocked", "detail": "Awaiting human approval"},
        ],
        "correlation_id": CORRELATION_ID,
    }

    baselines = [
        {
            "baseline_id": BASELINE_ID,
            "name": BASELINE_NAME,
            "version": 11,
            "model": BASELINE_NAME,
            "application": "customer-support-agent",
            "dataset_id": DATASET_ID,
            "evaluation_suite": "rag-quality+security",
            "created_at": "2026-08-01T09:00:00Z",
            "active": True,
            "archived": False,
            "owner": "platform-evals",
            "metrics": {r["metric"]: r["baseline"] for r in regressions},
            "evidence": ["ev_baseline_seed_v11"],
            "source": DEMO_SOURCE,
            "mutable": False,
        },
        {
            "baseline_id": "bl_cs_agent_v10_001",
            "name": "customer-support-agent-v10",
            "version": 10,
            "model": "customer-support-agent-v10",
            "application": "customer-support-agent",
            "dataset_id": DATASET_ID,
            "evaluation_suite": "rag-quality+security",
            "created_at": "2026-06-15T09:00:00Z",
            "active": False,
            "archived": True,
            "owner": "platform-evals",
            "metrics": {
                "groundedness": 0.89,
                "hallucination_rate": 0.05,
                "accuracy": 0.86,
                "latency_p95_ms": 900.0,
                "answer_relevancy": 0.88,
            },
            "evidence": ["ev_baseline_seed_v10"],
            "source": DEMO_SOURCE,
            "mutable": False,
        },
    ]

    approvals = [
        {
            "approval_id": APPROVAL_ID,
            "run_id": RUN_ID,
            "experiment_id": EXPERIMENT_ID,
            "candidate": CANDIDATE_MODEL,
            "risk_level": "high",
            "policy_reason": "groundedness below minimum; hallucination ceiling exceeded",
            "regression_summary": "2 regressions (1 critical, 1 high)",
            "evidence_available": True,
            "requester": "ci-bot@evalforge.local",
            "reviewer": None,
            "decision_state": "PENDING",
            "timestamp": "2026-09-22T10:15:14Z",
            "source": DEMO_SOURCE,
            "note": "Human review is a control boundary — agents cannot self-approve.",
        }
    ]

    audit = [
        {
            "event_id": "aud_001",
            "timestamp": "2026-09-22T10:14:40Z",
            "actor": "ci-bot@evalforge.local",
            "action": "experiment.started",
            "entity": "run",
            "entity_id": RUN_ID,
            "decision": None,
            "policy": None,
            "correlation_id": CORRELATION_ID,
            "source": DEMO_SOURCE,
        },
        {
            "event_id": "aud_002",
            "timestamp": "2026-09-22T10:15:11Z",
            "actor": "system:regression_engine",
            "action": "regression.detected",
            "entity": "run",
            "entity_id": RUN_ID,
            "decision": None,
            "policy": None,
            "correlation_id": CORRELATION_ID,
            "before": None,
            "after": {"critical": 1, "high": 1},
            "source": DEMO_SOURCE,
        },
        {
            "event_id": "aud_003",
            "timestamp": "2026-09-22T10:15:12Z",
            "actor": "system:policy_engine",
            "action": "policy.evaluated",
            "entity": "policy",
            "entity_id": POLICY_NAME,
            "decision": "REVIEW",
            "policy": f"{POLICY_NAME}@{POLICY_VERSION}",
            "correlation_id": CORRELATION_ID,
            "source": DEMO_SOURCE,
        },
        {
            "event_id": "aud_004",
            "timestamp": "2026-09-22T10:15:14Z",
            "actor": "system:orchestrator",
            "action": "approval.requested",
            "entity": "approval",
            "entity_id": APPROVAL_ID,
            "decision": "PENDING",
            "policy": f"{POLICY_NAME}@{POLICY_VERSION}",
            "correlation_id": CORRELATION_ID,
            "source": DEMO_SOURCE,
        },
    ]

    overview = {
        "window": "last_7_days",
        "source": DEMO_SOURCE,
        "counts": {
            "runs": 12,
            "allow": 7,
            "warn": 1,
            "review": 3,
            "deny": 1,
        },
        "regression_rate": 0.33,
        "policy_failure_rate": 0.33,
        "avg_latency_seconds": 41.2,
        "avg_cost_usd": None,
        "cost_note": "Cost tracking not instrumented in this build",
        "active_baseline": BASELINE_NAME,
        "latest_candidate": CANDIDATE_MODEL,
        "critical_regressions": 1,
        "pending_reviews": 1,
        "system_health": {"api": "ok", "ci": "passing", "control_plane": "partial"},
        "release_readiness": {
            "candidate": CANDIDATE_MODEL,
            "baseline": BASELINE_NAME,
            "evaluation_status": "SUCCEEDED",
            "regression_status": "REGRESSIONS_DETECTED",
            "policy_decision": "REVIEW",
            "human_approval": "PENDING",
            "final_release_state": "BLOCKED_PENDING_REVIEW",
        },
        "recent_policy_decisions": [
            {"run_id": RUN_ID, "decision": "REVIEW", "at": "2026-09-22T10:15:12Z"},
            {"run_id": "run_cs_agent_v12_000", "decision": "ALLOW", "at": "2026-09-20T16:02:00Z"},
            {"run_id": "run_cs_agent_v11_hotfix", "decision": "DENY", "at": "2026-09-18T11:40:00Z"},
        ],
        "recent_failed_evaluations": [
            {"run_id": "run_cs_agent_v11_hotfix", "status": "POLICY_REJECTED", "at": "2026-09-18T11:40:00Z"},
        ],
    }

    research = {
        "source": DEMO_SOURCE,
        "maturity": "partial",
        "benchmark_version": "support-golden-v3",
        "dataset_size": 128,
        "evaluation_categories": ["rag", "safety", "quality"],
        "model": CANDIDATE_MODEL,
        "metrics": {
            "groundedness": 0.82,
            "accuracy": 0.91,
            "hallucination_rate": 0.11,
        },
        "confidence_intervals": {
            "accuracy": {"low": 0.87, "high": 0.94, "note": "bootstrap CI from research module (illustrative)"},
        },
        "ablation_results": [
            {"system": "rule_baseline", "accuracy": 0.74},
            {"system": "evalforge_hybrid", "accuracy": 0.88},
        ],
        "failure_analysis": "Hallucination spikes on multi-hop policy questions; groundedness drops when retrieval returns thin evidence.",
        "reproducibility": {
            "command": "python -m research.run_analysis research/example_predictions.csv --systems rule_baseline evalforge_hybrid --compare rule_baseline evalforge_hybrid --seed 42",
            "artifacts": ["research/RESEARCH_PLAN.md", "research/example_predictions.csv", "CITATION.cff"],
        },
    }

    policy_catalog = {
        "name": POLICY_NAME,
        "version": POLICY_VERSION,
        "source": DEMO_SOURCE,
        "rules": [
            {
                "rule_id": "P-014-groundedness-minimum",
                "metric": "groundedness",
                "condition": "gte",
                "threshold": 0.85,
                "action": "REVIEW",
            },
            {
                "rule_id": "P-021-hallucination-ceiling",
                "metric": "hallucination_rate",
                "condition": "lte",
                "threshold": 0.08,
                "action": "REVIEW",
            },
            {
                "rule_id": "P-003-critical-security",
                "category": "security",
                "condition": "count_equals",
                "threshold": 0,
                "severity": "critical",
                "action": "DENY",
            },
        ],
    }

    return deepcopy(
        {
            "overview": overview,
            "runs": [run],
            "baselines": baselines,
            "evidence": evidence,
            "approvals": approvals,
            "audit": audit,
            "research": research,
            "policy_catalog": policy_catalog,
            "settings": {
                "maturity_labels": {
                    "overview": "demo_fixture",
                    "runs": "demo_fixture + live_cp_when_available",
                    "baselines": "demo_fixture + in_memory_cp",
                    "approvals": "prototype",
                    "audit": "demo_fixture",
                    "research": "partial_wired",
                    "settings": "read_only",
                },
                "persistence": "Control-plane operator demo fixtures are in-process. Workbench data uses SQLite.",
                "workbench_url": "/workbench",
            },
        }
    )

"""Operator console service — fixtures + live control-plane overlays."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.control_plane import api as cp_api
from app.control_plane.operator_fixtures import DEMO_SOURCE, RUN_ID, build_demo_world

_WORLD: dict[str, Any] | None = None


def ensure_seeded() -> dict[str, Any]:
    global _WORLD
    if _WORLD is None:
        _WORLD = build_demo_world()
    return _WORLD


def reset_demo() -> dict[str, Any]:
    global _WORLD
    _WORLD = build_demo_world()
    return _WORLD


def _merge_live_runs(world: dict[str, Any]) -> list[dict[str, Any]]:
    runs = list(world["runs"])
    known = {r["run_id"] for r in runs}
    for run_id, result in cp_api._RUNS.items():  # noqa: SLF001 — intentional operator overlay
        if run_id in known:
            continue
        run = result.run.model_dump(mode="json")
        runs.append(
            {
                "run_id": run_id,
                "experiment_id": run.get("experiment_id"),
                "candidate": (result.manifest.candidate if result.manifest else {}).get("model")
                if result.manifest
                else None,
                "model": (result.manifest.candidate if result.manifest else {}).get("model")
                if result.manifest
                else None,
                "dataset_id": result.manifest.dataset_version if result.manifest else None,
                "evaluation_suite": "live-control-plane",
                "baseline_version": (result.baseline.name if result.baseline else None),
                "started_at": run.get("started_at"),
                "completed_at": run.get("completed_at"),
                "duration_seconds": None,
                "status": run.get("state"),
                "overall_result": result.policy.decision.value if result.policy else run.get("state"),
                "policy_decision": result.policy.decision.value if result.policy else None,
                "environment": "local",
                "source": "live_control_plane",
                "metrics": result.metrics,
                "regressions": result.regressions.model_dump(mode="json") if result.regressions else None,
                "policy": result.policy.model_dump(mode="json") if result.policy else None,
                "manifest": result.manifest.model_dump(mode="json") if result.manifest else None,
            }
        )
    return runs


def get_overview() -> dict[str, Any]:
    world = ensure_seeded()
    overview = deepcopy(world["overview"])
    overview["live_run_count"] = len(cp_api._RUNS)  # noqa: SLF001
    return overview


def list_runs(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    world = ensure_seeded()
    runs = _merge_live_runs(world)
    filters = filters or {}
    out = []
    for run in runs:
        if filters.get("model") and filters["model"] not in str(run.get("model") or run.get("candidate") or ""):
            continue
        if filters.get("dataset") and filters["dataset"] not in str(run.get("dataset_id") or ""):
            continue
        if filters.get("policy_decision") and filters["policy_decision"] != run.get("policy_decision"):
            continue
        if filters.get("result") and filters["result"] != run.get("overall_result"):
            continue
        if filters.get("environment") and filters["environment"] != run.get("environment"):
            continue
        out.append(
            {
                "run_id": run["run_id"],
                "candidate": run.get("candidate") or run.get("model"),
                "dataset": run.get("dataset_id"),
                "evaluation_suite": run.get("evaluation_suite"),
                "baseline_version": run.get("baseline_version") or run.get("baseline_ref"),
                "started_at": run.get("started_at"),
                "duration_seconds": run.get("duration_seconds"),
                "status": run.get("status"),
                "overall_result": run.get("overall_result"),
                "policy_decision": run.get("policy_decision"),
                "environment": run.get("environment"),
                "source": run.get("source"),
            }
        )
    return out


def get_run(run_id: str) -> dict[str, Any] | None:
    world = ensure_seeded()
    for run in _merge_live_runs(world):
        if run["run_id"] == run_id:
            return deepcopy(run)
    live = cp_api.get_run(run_id)
    return live


def list_baselines() -> list[dict[str, Any]]:
    world = ensure_seeded()
    items = deepcopy(world["baselines"])
    for b in cp_api.list_baselines():
        items.append({**b, "source": "live_control_plane", "mutable": False})
    return items


def get_regressions(run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or RUN_ID
    run = get_run(run_id)
    if not run:
        return {"run_id": run_id, "has_regression": False, "results": [], "error": "not_found"}
    reg = run.get("regressions") or {"has_regression": False, "results": []}
    return {"run_id": run_id, "candidate": run.get("candidate"), "baseline": run.get("baseline_version"), **reg}


def get_policy(run_id: str | None = None) -> dict[str, Any]:
    world = ensure_seeded()
    run_id = run_id or RUN_ID
    run = get_run(run_id)
    catalog = deepcopy(world["policy_catalog"])
    if not run:
        return {"catalog": catalog, "decision": None, "error": "not_found"}
    return {
        "run_id": run_id,
        "catalog": catalog,
        "decision": run.get("policy"),
        "timeline": [
            {
                "at": m.get("timestamp"),
                "rule_id": m.get("rule_id"),
                "reason": m.get("reason"),
                "action": m.get("action"),
                "evidence": m.get("matched_evidence"),
            }
            for m in (run.get("policy") or {}).get("matches") or []
        ],
    }


def list_evidence(run_id: str | None = None, experiment_id: str | None = None) -> list[dict[str, Any]]:
    world = ensure_seeded()
    items = deepcopy(world["evidence"])
    if experiment_id:
        items.extend(cp_api.export_evidence(experiment_id))
    if run_id:
        items = [e for e in items if e.get("run_id") == run_id or run_id is None]
    return items


def list_approvals() -> list[dict[str, Any]]:
    return deepcopy(ensure_seeded()["approvals"])


def decide_approval(approval_id: str, outcome: str, reviewer: str, comment: str | None = None) -> dict[str, Any]:
    """Prototype human decision — does not claim durable audit guarantees."""
    world = ensure_seeded()
    outcome = outcome.upper()
    if outcome not in {"APPROVED", "REJECTED"}:
        raise ValueError("outcome must be APPROVED or REJECTED")
    if not reviewer or not reviewer.strip():
        raise ValueError("reviewer is required for human approval")
    if "ci-bot" in reviewer.lower():
        raise ValueError("AI/CI actors cannot approve their own release decisions")
    for item in world["approvals"]:
        if item["approval_id"] == approval_id:
            if item["decision_state"] != "PENDING":
                raise ValueError("approval is not pending")
            item["decision_state"] = outcome
            item["reviewer"] = reviewer
            item["comment"] = comment
            item["decided_at"] = "2026-09-22T12:00:00Z"
            world["audit"].append(
                {
                    "event_id": f"aud_human_{outcome.lower()}",
                    "timestamp": item["decided_at"],
                    "actor": reviewer,
                    "action": f"approval.{outcome.lower()}",
                    "entity": "approval",
                    "entity_id": approval_id,
                    "decision": outcome,
                    "policy": "production-agent-release@1",
                    "correlation_id": item.get("run_id"),
                    "source": "prototype",
                }
            )
            # Update release chain on primary demo run
            for run in world["runs"]:
                if run["run_id"] == item["run_id"]:
                    run["release_chain"][-2] = {
                        "step": "Human Review",
                        "status": "completed",
                        "detail": f"{outcome} by {reviewer}",
                    }
                    run["release_chain"][-1] = {
                        "step": "Release Decision",
                        "status": "released" if outcome == "APPROVED" else "blocked",
                        "detail": outcome,
                    }
                    world["overview"]["release_readiness"]["human_approval"] = outcome
                    world["overview"]["release_readiness"]["final_release_state"] = (
                        "RELEASED" if outcome == "APPROVED" else "REJECTED"
                    )
                    world["overview"]["pending_reviews"] = 0
            return deepcopy(item)
    raise KeyError("approval not found")


def list_audit(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    world = ensure_seeded()
    filters = filters or {}
    out = []
    for event in world["audit"]:
        if filters.get("actor") and filters["actor"] not in str(event.get("actor") or ""):
            continue
        if filters.get("event_type") and filters["event_type"] not in str(event.get("action") or ""):
            continue
        if filters.get("entity") and filters["entity"] != event.get("entity"):
            continue
        out.append(deepcopy(event))
    return out


def get_research() -> dict[str, Any]:
    return deepcopy(ensure_seeded()["research"])


def get_settings() -> dict[str, Any]:
    return deepcopy(ensure_seeded()["settings"])

"""Agent Reliability Platform — local-first EvalForge bridge.

Versioned interface to cooperate with ci-failure-orchestrator without merging
repositories. Deterministic sandbox + policy; never auto-merges or deploys.
"""

from __future__ import annotations

from agent_reliability.interface_v1 import (
    INTERFACE_ID,
    INTERFACE_VERSION,
    GateDecision,
    map_to_ci_failure_orchestrator,
)
from agent_reliability.pipeline import run_local_reliability_pipeline

__all__ = [
    "INTERFACE_ID",
    "INTERFACE_VERSION",
    "GateDecision",
    "map_to_ci_failure_orchestrator",
    "run_local_reliability_pipeline",
]

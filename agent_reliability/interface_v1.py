"""Versioned interface between EvalForge and ci-failure-orchestrator.

INTERFACE_VERSION bumps only when fields or decision semantics change.
This module is the contract surface — do not import ci-failure-orchestrator.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

INTERFACE_ID = "evalforge.ci_failure_bridge"
INTERFACE_VERSION = "1.0.0"

# Peer vocabulary (documented only; not imported):
# ci-failure-orchestrator PolicyOutcome: APPROVE | REJECT | ESCALATE
CFO_APPROVE = "APPROVE"
CFO_REJECT = "REJECT"
CFO_ESCALATE = "ESCALATE"


class GateDecision(str, Enum):
    """EvalForge Agent Reliability gate (local-first)."""

    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


def map_to_ci_failure_orchestrator(decision: GateDecision) -> str:
    """Map ARP decisions onto ci-failure-orchestrator policy outcomes."""
    if decision is GateDecision.PASS:
        return CFO_APPROVE
    if decision is GateDecision.WARN:
        return CFO_ESCALATE
    if decision is GateDecision.BLOCK:
        return CFO_REJECT
    raise AssertionError(f"unhandled decision: {decision!r}")


class CandidateChange(BaseModel):
    """Proposed coding-agent change under evaluation."""

    change_id: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=4000)
    files_touched: list[str] = Field(default_factory=list)
    patch_text: str = Field(default="", max_length=200_000)
    # Apply intents — ignored for merge/deploy; missing auth fail-closes if True.
    request_merge: bool = False
    request_deploy: bool = False
    authorization_token: str | None = None
    actor: str = Field(default="local-fixture", max_length=120)

    @field_validator("files_touched")
    @classmethod
    def _bounded_files(cls, value: list[str]) -> list[str]:
        if len(value) > 200:
            raise ValueError("files_touched exceeds 200 entries")
        return value


class SandboxTestResult(BaseModel):
    passed: bool
    exit_code: int
    tests_collected: int | None = None
    tests_failed: int | None = None
    duration_ms: float | None = None
    command: list[str] = Field(default_factory=list)
    stdout_redacted: str = ""
    stderr_redacted: str = ""
    error: str | None = None


class RegressionAssessment(BaseModel):
    baseline_passed: bool
    candidate_passed: bool
    regressions: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    compared: bool = True


class PolicyRuleMatch(BaseModel):
    rule_id: str
    condition: str
    action: GateDecision
    observed: Any = None


class PolicyDecisionRecord(BaseModel):
    decision: GateDecision
    matched_rules: list[PolicyRuleMatch] = Field(default_factory=list)
    rationale: str
    allow_merge: Literal[False] = False
    allow_deploy: Literal[False] = False
    peer_outcome: str  # APPROVE | REJECT | ESCALATE


class AuditEvidenceBundle(BaseModel):
    interface_id: str = INTERFACE_ID
    interface_version: str = INTERFACE_VERSION
    run_id: str
    change_id: str
    decision: GateDecision
    peer_outcome: str
    sandbox: SandboxTestResult
    regression: RegressionAssessment
    policy: PolicyDecisionRecord
    redactions_applied: list[str] = Field(default_factory=list)
    data_label: Literal["local_benchmark", "synthetic"] = "synthetic"
    production_ready_claim: Literal[False] = False
    artifact_sha256: str | None = None


class ReliabilityRequest(BaseModel):
    """Inbound envelope for the local pipeline."""

    interface_id: str = INTERFACE_ID
    interface_version: str = INTERFACE_VERSION
    candidate: CandidateChange
    # Optional attacker-controlled field; pipeline must ignore for decisioning.
    claimed_decision: GateDecision | None = None
    expected_authorization_token: str | None = None


class ReliabilityResponse(BaseModel):
    interface_id: str = INTERFACE_ID
    interface_version: str = INTERFACE_VERSION
    evidence: AuditEvidenceBundle

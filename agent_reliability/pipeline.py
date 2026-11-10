"""Deterministic local-first reliability pipeline.

candidate change → sandboxed tests → regression assessment → PASS/WARN/BLOCK
→ redacted audit evidence. Never merges or deploys.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from agent_reliability.interface_v1 import (
    INTERFACE_ID,
    INTERFACE_VERSION,
    AuditEvidenceBundle,
    CandidateChange,
    GateDecision,
    PolicyRuleMatch,
    RegressionAssessment,
    ReliabilityRequest,
    ReliabilityResponse,
    SandboxTestResult,
    map_to_ci_failure_orchestrator,
)
from agent_reliability.policy import evaluate_gate
from agent_reliability.redaction import redact_text
from agent_reliability.sandbox import cleanup_workspace, materialize_workspace, run_pytest
from agent_reliability.security import authorization_failures, injection_hits

GOOD_CALC = Path(__file__).resolve().parent / "fixtures" / "good_calc.py"


def _block_response(
    *,
    change_id: str,
    matched: list[PolicyRuleMatch],
    rationale: str,
    sandbox: SandboxTestResult | None = None,
    regression: RegressionAssessment | None = None,
    redactions: list[str] | None = None,
) -> ReliabilityResponse:
    decision = GateDecision.BLOCK
    sandbox = sandbox or SandboxTestResult(passed=False, exit_code=-1, error="not_run")
    regression = regression or RegressionAssessment(
        baseline_passed=False, candidate_passed=False, compared=False
    )
    from agent_reliability.interface_v1 import PolicyDecisionRecord

    policy = PolicyDecisionRecord(
        decision=decision,
        matched_rules=matched,
        rationale=rationale,
        allow_merge=False,
        allow_deploy=False,
        peer_outcome=map_to_ci_failure_orchestrator(decision),
    )
    run_id = f"arp_{uuid4().hex[:12]}"
    evidence = AuditEvidenceBundle(
        run_id=run_id,
        change_id=change_id,
        decision=decision,
        peer_outcome=policy.peer_outcome,
        sandbox=sandbox,
        regression=regression,
        policy=policy,
        redactions_applied=redactions or [],
    )
    payload = evidence.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    evidence.artifact_sha256 = digest
    return ReliabilityResponse(evidence=evidence)


def assess_regression(baseline: SandboxTestResult, candidate: SandboxTestResult) -> RegressionAssessment:
    regressions: list[str] = []
    improvements: list[str] = []
    if baseline.passed and not candidate.passed:
        regressions.append("candidate_broke_passing_baseline")
    if (not baseline.passed) and candidate.passed:
        improvements.append("candidate_fixed_failing_baseline")
    if baseline.passed and candidate.passed:
        improvements.append("candidate_preserved_passing_suite")
    return RegressionAssessment(
        baseline_passed=baseline.passed,
        candidate_passed=candidate.passed,
        regressions=regressions,
        improvements=improvements,
        compared=True,
    )


def run_local_reliability_pipeline(
    request: ReliabilityRequest | dict,
    *,
    evidence_dir: Path | None = None,
) -> ReliabilityResponse:
    """Execute the local fixture pipeline and optionally persist evidence JSON."""
    try:
        req = request if isinstance(request, ReliabilityRequest) else ReliabilityRequest.model_validate(request)
    except ValidationError as exc:
        return _block_response(
            change_id="invalid",
            matched=[
                PolicyRuleMatch(
                    rule_id="ARP-INPUT-001",
                    condition="malformed ReliabilityRequest",
                    action=GateDecision.BLOCK,
                    observed=str(exc.errors()[:3]),
                )
            ],
            rationale="BLOCK. ARP-INPUT-001: malformed ReliabilityRequest",
        )

    if req.interface_id != INTERFACE_ID or req.interface_version != INTERFACE_VERSION:
        return _block_response(
            change_id=req.candidate.change_id,
            matched=[
                PolicyRuleMatch(
                    rule_id="ARP-IFACE-001",
                    condition="interface_id/version mismatch",
                    action=GateDecision.BLOCK,
                    observed={
                        "interface_id": req.interface_id,
                        "interface_version": req.interface_version,
                        "expected": [INTERFACE_ID, INTERFACE_VERSION],
                    },
                )
            ],
            rationale="BLOCK. ARP-IFACE-001: interface_id/version mismatch",
        )

    # Policy bypass attempt: claimed_decision is never honored.
    security_matches = authorization_failures(
        req.candidate, expected_token=req.expected_authorization_token
    )
    if req.claimed_decision is not None:
        security_matches.append(
            PolicyRuleMatch(
                rule_id="ARP-BYPASS-001",
                condition="claimed_decision is ignored; attempting to supply a decision is BLOCK",
                action=GateDecision.BLOCK,
                observed={"claimed_decision": req.claimed_decision.value},
            )
        )

    inj = injection_hits(req.candidate.summary) + injection_hits(req.candidate.patch_text)
    if inj:
        security_matches.append(
            PolicyRuleMatch(
                rule_id="ARP-INJECT-001",
                condition="prompt-injection or secret-exfil pattern in candidate text",
                action=GateDecision.BLOCK,
                observed={"pattern_count": len(inj)},
            )
        )

    # Early fail-closed on security before running code.
    if any(m.action is GateDecision.BLOCK for m in security_matches):
        policy = evaluate_gate(
            sandbox=SandboxTestResult(passed=False, exit_code=-1, error="blocked_before_sandbox"),
            regression=RegressionAssessment(
                baseline_passed=False, candidate_passed=False, compared=False
            ),
            security_matches=security_matches,
            evidence_complete=True,
        )
        return _finalize(
            req.candidate,
            sandbox=SandboxTestResult(passed=False, exit_code=-1, error="blocked_before_sandbox"),
            regression=RegressionAssessment(
                baseline_passed=False, candidate_passed=False, compared=False
            ),
            policy=policy,
            redactions=[],
            evidence_dir=evidence_dir,
        )

    baseline_ws = materialize_workspace(None)
    candidate_ws = None
    try:
        baseline = run_pytest(baseline_ws)
        candidate_ws = materialize_workspace(req.candidate.patch_text or None)
        # If no patch provided, candidate == baseline (still comparable).
        candidate = run_pytest(candidate_ws)
        regression = assess_regression(baseline, candidate)
        evidence_complete = bool(req.candidate.change_id) and candidate.command is not None
        policy = evaluate_gate(
            sandbox=candidate,
            regression=regression,
            security_matches=security_matches,
            evidence_complete=evidence_complete,
        )
        # Redact any leaked token material from patch when persisting.
        _, redactions = redact_text(req.candidate.patch_text or "")
        return _finalize(
            req.candidate,
            sandbox=candidate,
            regression=regression,
            policy=policy,
            redactions=redactions,
            evidence_dir=evidence_dir,
        )
    finally:
        cleanup_workspace(baseline_ws)
        if candidate_ws is not None:
            cleanup_workspace(candidate_ws)


def _finalize(
    candidate: CandidateChange,
    *,
    sandbox: SandboxTestResult,
    regression: RegressionAssessment,
    policy,
    redactions: list[str],
    evidence_dir: Path | None,
) -> ReliabilityResponse:
    run_id = f"arp_{uuid4().hex[:12]}"
    evidence = AuditEvidenceBundle(
        run_id=run_id,
        change_id=candidate.change_id,
        decision=policy.decision,
        peer_outcome=policy.peer_outcome,
        sandbox=sandbox,
        regression=regression,
        policy=policy,
        redactions_applied=redactions,
    )
    payload = evidence.model_dump(mode="json")
    evidence.artifact_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    response = ReliabilityResponse(evidence=evidence)
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / f"{run_id}.evidence.json"
        path.write_text(response.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return response


def load_good_patch() -> str:
    return GOOD_CALC.read_text(encoding="utf-8")

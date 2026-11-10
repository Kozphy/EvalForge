"""Deterministic PASS / WARN / BLOCK policy — fail closed by default."""

from __future__ import annotations

from agent_reliability.interface_v1 import (
    GateDecision,
    PolicyDecisionRecord,
    PolicyRuleMatch,
    RegressionAssessment,
    SandboxTestResult,
    map_to_ci_failure_orchestrator,
)


def evaluate_gate(
    *,
    sandbox: SandboxTestResult,
    regression: RegressionAssessment,
    security_matches: list[PolicyRuleMatch],
    evidence_complete: bool,
) -> PolicyDecisionRecord:
    matched: list[PolicyRuleMatch] = list(security_matches)
    decision = GateDecision.PASS

    if not evidence_complete:
        matched.append(
            PolicyRuleMatch(
                rule_id="ARP-EVID-001",
                condition="required evidence fields missing",
                action=GateDecision.BLOCK,
                observed={"evidence_complete": False},
            )
        )
        decision = GateDecision.BLOCK

    if sandbox.error == "sandbox_timeout":
        matched.append(
            PolicyRuleMatch(
                rule_id="ARP-SBOX-001",
                condition="sandbox timed out",
                action=GateDecision.BLOCK,
                observed={"exit_code": sandbox.exit_code},
            )
        )
        decision = GateDecision.BLOCK

    if not sandbox.passed:
        matched.append(
            PolicyRuleMatch(
                rule_id="ARP-TEST-001",
                condition="sandboxed tests did not pass",
                action=GateDecision.BLOCK,
                observed={"exit_code": sandbox.exit_code, "error": sandbox.error},
            )
        )
        decision = GateDecision.BLOCK

    if regression.compared and regression.regressions:
        matched.append(
            PolicyRuleMatch(
                rule_id="ARP-REG-001",
                condition="regression vs baseline",
                action=GateDecision.BLOCK,
                observed=regression.regressions,
            )
        )
        decision = GateDecision.BLOCK

    # WARN: baseline was already failing and candidate fixed it but took long — illustrative
    if (
        decision is GateDecision.PASS
        and sandbox.duration_ms is not None
        and sandbox.duration_ms > 15_000
    ):
        matched.append(
            PolicyRuleMatch(
                rule_id="ARP-PERF-001",
                condition="sandbox duration_ms > 15000",
                action=GateDecision.WARN,
                observed=sandbox.duration_ms,
            )
        )
        decision = GateDecision.WARN

    # Security matches always dominate toward BLOCK (already GateDecision.BLOCK).
    for item in security_matches:
        if item.action is GateDecision.BLOCK:
            decision = GateDecision.BLOCK

    if not matched and decision is GateDecision.PASS:
        rationale = "All local gates passed; merge/deploy remain disabled."
    else:
        parts = [f"{m.rule_id}: {m.condition} → {m.action.value}" for m in matched]
        rationale = f"{decision.value}. " + "; ".join(parts)

    return PolicyDecisionRecord(
        decision=decision,
        matched_rules=matched,
        rationale=rationale,
        allow_merge=False,
        allow_deploy=False,
        peer_outcome=map_to_ci_failure_orchestrator(decision),
    )

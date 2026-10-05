"""Provider-independent policy engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.control_plane.contracts import PolicyDecisionType, new_id
from app.control_plane.regression.engine import RegressionReport


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PolicyRule(BaseModel):
    id: str
    version: str = "1"
    metric: str | None = None
    category: str | None = None
    gte: float | None = None
    lte: float | None = None
    delta_gte: float | None = None
    severity_equals: str | None = None
    count_equals: int | None = None
    action: PolicyDecisionType = PolicyDecisionType.DENY


class PolicySpec(BaseModel):
    name: str
    version: str = "1"
    rules: list[PolicyRule] = Field(default_factory=list)


class PolicyRuleMatch(BaseModel):
    rule_id: str
    rule_version: str
    action: PolicyDecisionType
    reason: str
    matched_evidence: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class PolicyDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: new_id("pol"))
    policy_name: str
    policy_version: str
    decision: PolicyDecisionType
    matches: list[PolicyRuleMatch] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)


class PolicyEngine:
    def evaluate(
        self,
        policy: PolicySpec,
        *,
        metrics: dict[str, float],
        regressions: RegressionReport | None = None,
        security_findings: list[dict[str, Any]] | None = None,
    ) -> PolicyDecision:
        matches: list[PolicyRuleMatch] = []
        security_findings = security_findings or []
        for rule in policy.rules:
            matched = False
            reason = ""
            evidence: dict[str, Any] = {}
            if rule.metric and rule.gte is not None:
                value = metrics.get(rule.metric)
                evidence = {"metric": rule.metric, "value": value, "gte": rule.gte}
                if value is None or value < rule.gte:
                    matched = True
                    reason = f"{rule.metric} below minimum {rule.gte}"
            if rule.metric and rule.delta_gte is not None and regressions is not None:
                for item in regressions.results:
                    if item.metric == rule.metric and item.absolute_delta is not None:
                        evidence = {
                            "metric": rule.metric,
                            "absolute_delta": item.absolute_delta,
                            "delta_gte": rule.delta_gte,
                        }
                        if item.absolute_delta < rule.delta_gte:
                            matched = True
                            reason = f"{rule.metric} delta {item.absolute_delta} worse than {rule.delta_gte}"
            if rule.category == "security" and rule.severity_equals and rule.count_equals is not None:
                count = sum(
                    1
                    for f in security_findings
                    if str(f.get("severity", "")).lower() == rule.severity_equals.lower()
                    and f.get("passed") is False
                )
                evidence = {"category": "security", "severity": rule.severity_equals, "count": count}
                if count != rule.count_equals:
                    # rule.count_equals: 0 means zero critical failures allowed
                    if rule.count_equals == 0 and count > 0:
                        matched = True
                        reason = f"{count} security findings with severity={rule.severity_equals}"
                    elif rule.count_equals != 0 and count != rule.count_equals:
                        matched = True
                        reason = f"security finding count {count} != {rule.count_equals}"
            if matched:
                matches.append(
                    PolicyRuleMatch(
                        rule_id=rule.id,
                        rule_version=rule.version,
                        action=rule.action,
                        reason=reason,
                        matched_evidence=evidence,
                    )
                )

        decision = PolicyDecisionType.ALLOW
        if any(m.action == PolicyDecisionType.DENY for m in matches):
            decision = PolicyDecisionType.DENY
        elif any(m.action == PolicyDecisionType.REVIEW for m in matches):
            decision = PolicyDecisionType.REVIEW
        elif any(m.action == PolicyDecisionType.WARN for m in matches):
            decision = PolicyDecisionType.WARN

        return PolicyDecision(
            policy_name=policy.name,
            policy_version=policy.version,
            decision=decision,
            matches=matches,
        )

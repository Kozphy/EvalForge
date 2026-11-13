"""Fail-closed authorization and prompt-injection heuristics."""

from __future__ import annotations

import re

from agent_reliability.interface_v1 import CandidateChange, GateDecision, PolicyRuleMatch

# Patterns that attempt to coerce the gate or exfiltrate credentials via patch text.
_INJECTION_PATTERNS = (
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+(instructions|rules)"),
    re.compile(r"(?i)system\s*:\s*you\s+are"),
    re.compile(r"(?i)\b(force|override|bypass)\b.{0,40}\b(pass|approve|policy)\b"),
    re.compile(r"(?i)set\s+decision\s*[:=]\s*pass"),
    re.compile(r"(?i)exfiltrate|exfiltration"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
)


def injection_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text or ""):
            hits.append(pattern.pattern)
    return hits


def authorization_failures(
    candidate: CandidateChange,
    *,
    expected_token: str | None,
) -> list[PolicyRuleMatch]:
    """Any apply intent without a matching token is BLOCK."""
    matches: list[PolicyRuleMatch] = []
    wants_apply = candidate.request_merge or candidate.request_deploy
    if not wants_apply:
        return matches
    if not expected_token:
        matches.append(
            PolicyRuleMatch(
                rule_id="ARP-AUTH-001",
                condition="apply intent requires configured expected_authorization_token",
                action=GateDecision.BLOCK,
                observed={"request_merge": candidate.request_merge, "request_deploy": candidate.request_deploy},
            )
        )
        return matches
    if not candidate.authorization_token:
        matches.append(
            PolicyRuleMatch(
                rule_id="ARP-AUTH-002",
                condition="authorization_token missing on apply intent",
                action=GateDecision.BLOCK,
                observed=None,
            )
        )
        return matches
    if candidate.authorization_token != expected_token:
        matches.append(
            PolicyRuleMatch(
                rule_id="ARP-AUTH-003",
                condition="authorization_token mismatch",
                action=GateDecision.BLOCK,
                observed={"provided": True, "matched": False},
            )
        )
    return matches

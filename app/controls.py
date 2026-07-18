"""Runtime controls for groundedness, citation integrity, and release decisions.

The controls layer is deliberately dependency-light and local-first. It does not
claim to prove truth. It converts grader output, deterministic findings, and the
retrieved evidence set into an explicit allow/review/block decision that can be
audited and routed to the existing human-review workflow.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from .schemas import GraderOutput, RuleFinding

ControlAction = Literal["allow", "review", "block"]


class ControlPolicy(BaseModel):
    """Release policy snapshotted with each run."""

    min_groundedness: float = Field(default=0.75, ge=0.0, le=1.0)
    min_citation_coverage: float = Field(default=0.75, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    block_on_contradiction: bool = True
    block_on_invalid_citation: bool = True
    block_on_major_rule_failure: bool = True


class ControlFinding(BaseModel):
    control: str
    passed: bool
    action: ControlAction
    message: str
    observed: float | int | str | list[str] | None = None
    threshold: float | int | str | None = None


class ControlReport(BaseModel):
    action: ControlAction
    release_allowed: bool
    needs_human_review: bool
    groundedness: float = Field(ge=0.0, le=1.0)
    citation_coverage: float = Field(ge=0.0, le=1.0)
    retrieval_max_score: float = Field(ge=0.0, le=1.0)
    claim_counts: dict[str, int]
    invalid_citation_ids: list[str]
    findings: list[ControlFinding]


def _max_action(current: ControlAction, candidate: ControlAction) -> ControlAction:
    rank = {"allow": 0, "review": 1, "block": 2}
    return candidate if rank[candidate] > rank[current] else current


def evaluate_controls(
    output: GraderOutput,
    rule_findings: list[RuleFinding],
    evidence: list[dict],
    policy: ControlPolicy,
) -> ControlReport:
    """Evaluate a conservative release decision without another LLM call."""

    evidence_ids = {
        str(item.get("chunk_id"))
        for item in evidence
        if item.get("chunk_id") is not None
    }
    retrieval_max_score = max(
        (float(item.get("score") or 0.0) for item in evidence),
        default=0.0,
    )

    counts = Counter(claim.verdict for claim in output.claims)
    claim_count = len(output.claims)
    supported_count = counts.get("supported", 0)

    valid_cited_claims = 0
    invalid_ids: set[str] = set()
    for claim in output.claims:
        claim_ids = [str(value) for value in claim.evidence_chunk_ids]
        if claim_ids and all(value in evidence_ids for value in claim_ids):
            valid_cited_claims += 1
        invalid_ids.update(value for value in claim_ids if value not in evidence_ids)

    # No factual claims means there is no claim-level grounding failure to score.
    groundedness = supported_count / claim_count if claim_count else 1.0
    citation_coverage = valid_cited_claims / claim_count if claim_count else 1.0
    failed_major_rules = [
        finding.rule_type
        for finding in rule_findings
        if not finding.passed and finding.severity == "major"
    ]

    action: ControlAction = "allow"
    findings: list[ControlFinding] = []

    contradiction_count = counts.get("contradicted", 0)
    contradiction_action: ControlAction = (
        "block" if policy.block_on_contradiction else "review"
    )
    contradiction_passed = contradiction_count == 0
    findings.append(
        ControlFinding(
            control="claim_contradiction",
            passed=contradiction_passed,
            action="allow" if contradiction_passed else contradiction_action,
            observed=contradiction_count,
            threshold=0,
            message=(
                "No contradicted claims were reported."
                if contradiction_passed
                else f"{contradiction_count} contradicted claim(s) require intervention."
            ),
        )
    )
    if not contradiction_passed:
        action = _max_action(action, contradiction_action)

    invalid_action: ControlAction = (
        "block" if policy.block_on_invalid_citation else "review"
    )
    invalid_passed = not invalid_ids
    findings.append(
        ControlFinding(
            control="citation_integrity",
            passed=invalid_passed,
            action="allow" if invalid_passed else invalid_action,
            observed=sorted(invalid_ids),
            threshold="all cited chunk IDs must exist in retrieved evidence",
            message=(
                "All claim citation IDs resolve to retrieved evidence."
                if invalid_passed
                else "One or more claim citation IDs are absent from the retrieved evidence set."
            ),
        )
    )
    if not invalid_passed:
        action = _max_action(action, invalid_action)

    major_rule_action: ControlAction = (
        "block" if policy.block_on_major_rule_failure else "review"
    )
    major_rule_passed = not failed_major_rules
    findings.append(
        ControlFinding(
            control="major_rule_failures",
            passed=major_rule_passed,
            action="allow" if major_rule_passed else major_rule_action,
            observed=failed_major_rules,
            threshold=0,
            message=(
                "No major deterministic rule failed."
                if major_rule_passed
                else "A core deterministic requirement failed."
            ),
        )
    )
    if not major_rule_passed:
        action = _max_action(action, major_rule_action)

    groundedness_passed = groundedness >= policy.min_groundedness
    findings.append(
        ControlFinding(
            control="groundedness",
            passed=groundedness_passed,
            action="allow" if groundedness_passed else "review",
            observed=round(groundedness, 4),
            threshold=policy.min_groundedness,
            message=(
                "Supported-claim ratio meets the configured threshold."
                if groundedness_passed
                else "Supported-claim ratio is below the configured threshold."
            ),
        )
    )
    if not groundedness_passed:
        action = _max_action(action, "review")

    citation_coverage_passed = citation_coverage >= policy.min_citation_coverage
    findings.append(
        ControlFinding(
            control="citation_coverage",
            passed=citation_coverage_passed,
            action="allow" if citation_coverage_passed else "review",
            observed=round(citation_coverage, 4),
            threshold=policy.min_citation_coverage,
            message=(
                "Claim citation coverage meets the configured threshold."
                if citation_coverage_passed
                else "Too many claims lack resolvable evidence citations."
            ),
        )
    )
    if not citation_coverage_passed:
        action = _max_action(action, "review")

    confidence_passed = output.confidence >= policy.min_confidence
    findings.append(
        ControlFinding(
            control="grader_confidence",
            passed=confidence_passed,
            action="allow" if confidence_passed else "review",
            observed=round(output.confidence, 4),
            threshold=policy.min_confidence,
            message=(
                "Grader confidence meets the configured threshold."
                if confidence_passed
                else "Grader confidence is below the configured threshold."
            ),
        )
    )
    if not confidence_passed:
        action = _max_action(action, "review")

    unresolved_count = counts.get("unsupported", 0) + counts.get("uncertain", 0)
    unresolved_passed = unresolved_count == 0
    findings.append(
        ControlFinding(
            control="unresolved_claims",
            passed=unresolved_passed,
            action="allow" if unresolved_passed else "review",
            observed=unresolved_count,
            threshold=0,
            message=(
                "No unsupported or uncertain claims remain."
                if unresolved_passed
                else "Unsupported or uncertain claims require human review."
            ),
        )
    )
    if not unresolved_passed:
        action = _max_action(action, "review")

    return ControlReport(
        action=action,
        release_allowed=action == "allow",
        needs_human_review=action != "allow",
        groundedness=round(groundedness, 4),
        citation_coverage=round(citation_coverage, 4),
        retrieval_max_score=round(retrieval_max_score, 4),
        claim_counts=dict(sorted(counts.items())),
        invalid_citation_ids=sorted(invalid_ids),
        findings=findings,
    )

from __future__ import annotations

from app.controls import ControlPolicy, evaluate_controls
from app.schemas import ClaimAssessment, GraderOutput, RuleFinding


def _output(
    *,
    verdict: str = "pass",
    severity: str = "no_issue",
    confidence: float = 0.9,
    claims: list[ClaimAssessment] | None = None,
) -> GraderOutput:
    """Build a minimal GraderOutput fixture for control tests.

    Args:
        verdict: Grader verdict string (e.g. "pass", "fail", "review").
        severity: Severity label (e.g. "no_issue", "minor", "major").
        confidence: Grader confidence score (0.0–1.0).
        claims: Optional list of ClaimAssessment objects.

    Returns:
        GraderOutput with the given fields and sensible defaults.
    """
    return GraderOutput(
        verdict=verdict,
        severity=severity,
        score=1.0,
        confidence=confidence,
        reason="test",
        claims=claims or [],
        needs_human_review=False,
    )


def _claim(verdict: str, ids: list[str]) -> ClaimAssessment:
    """Build a minimal ClaimAssessment fixture for control tests.

    Args:
        verdict: Claim verdict (e.g. "supported", "unsupported", "contradicted").
        ids: List of evidence chunk IDs cited by this claim.

    Returns:
        ClaimAssessment with a canonical finance claim text and the given verdict.
    """
    return ClaimAssessment(
        claim="Revenue is recognized when the performance obligation is satisfied.",
        verdict=verdict,
        confidence=0.9,
        evidence_chunk_ids=ids,
        reason="test",
    )


def test_controls_allow_supported_claim_with_valid_evidence() -> None:
    """A supported claim with a valid evidence chunk ID receives an allow decision.

    Verifies that when all claims are supported and their cited chunk IDs are
    present in the evidence set, evaluate_controls returns action="allow",
    release_allowed=True, and perfect groundedness and citation coverage scores.
    """
    report = evaluate_controls(
        _output(claims=[_claim("supported", ["doc-1-chunk-0"])]),
        [],
        [{"chunk_id": "doc-1-chunk-0", "score": 0.82}],
        ControlPolicy(),
    )
    assert report.action == "allow"
    assert report.release_allowed is True
    assert report.groundedness == 1.0
    assert report.citation_coverage == 1.0


def test_controls_block_invalid_citation_id() -> None:
    """A claim citing a chunk ID not in the evidence set is blocked.

    Verifies that when a claim references a chunk ID that does not exist in the
    retrieved evidence, evaluate_controls returns action="block",
    release_allowed=False, and records the invented ID in invalid_citation_ids.
    """
    report = evaluate_controls(
        _output(claims=[_claim("supported", ["invented-chunk"])]),
        [],
        [{"chunk_id": "doc-1-chunk-0", "score": 0.82}],
        ControlPolicy(),
    )
    assert report.action == "block"
    assert report.release_allowed is False
    assert report.invalid_citation_ids == ["invented-chunk"]


def test_controls_block_contradicted_claim() -> None:
    """A contradicted claim triggers a block decision.

    Verifies that when any claim verdict is "contradicted" and the default
    policy has block_on_contradiction=True, evaluate_controls returns
    action="block" and records the contradiction count correctly.
    """
    report = evaluate_controls(
        _output(
            verdict="fail",
            severity="major",
            claims=[_claim("contradicted", ["doc-1-chunk-0"])],
        ),
        [],
        [{"chunk_id": "doc-1-chunk-0", "score": 0.82}],
        ControlPolicy(),
    )
    assert report.action == "block"
    assert report.claim_counts["contradicted"] == 1


def test_controls_review_unsupported_claim() -> None:
    """An unsupported claim routes to human review rather than blocking.

    Verifies that an unsupported claim without evidence produces action="review",
    needs_human_review=True, and groundedness=0.0 (no supported claims).
    """
    report = evaluate_controls(
        _output(
            verdict="review",
            severity="minor",
            claims=[_claim("unsupported", [])],
        ),
        [],
        [],
        ControlPolicy(),
    )
    assert report.action == "review"
    assert report.needs_human_review is True
    assert report.groundedness == 0.0


def test_controls_block_major_rule_failure() -> None:
    """A major deterministic rule failure triggers a block decision.

    Verifies that when rule_findings contains a failed finding with
    severity="major" and the default policy has block_on_major_rule_failure=True,
    evaluate_controls returns action="block".
    """
    finding = RuleFinding(
        rule_type="required_phrase",
        passed=False,
        severity="major",
        message="missing",
    )
    report = evaluate_controls(
        _output(),
        [finding],
        [],
        ControlPolicy(),
    )
    assert report.action == "block"

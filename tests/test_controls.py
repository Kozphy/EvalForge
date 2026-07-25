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
    return ClaimAssessment(
        claim="Revenue is recognized when the performance obligation is satisfied.",
        verdict=verdict,
        confidence=0.9,
        evidence_chunk_ids=ids,
        reason="test",
    )


def test_controls_allow_supported_claim_with_valid_evidence() -> None:
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

from app.research_assurance import Criterion, GateStatus, evaluate_gate, required_criteria


def test_gate_passes_when_all_applicable_checks_pass():
    result = evaluate_gate(
        "problem_ready",
        [
            Criterion("PROBLEM_FORMALIZED", GateStatus.PASS),
            Criterion("SCOPE_DEFINED", GateStatus.PASS),
            Criterion("OPTIONAL", GateStatus.NOT_APPLICABLE),
        ],
    )
    assert result.status is GateStatus.PASS
    assert result.failed == ()


def test_unknown_fails_closed_by_default():
    result = evaluate_gate(
        "verification_success",
        [Criterion("FORMAL_CHECK_PASS", GateStatus.UNKNOWN)],
    )
    assert result.status is GateStatus.FAIL
    assert result.unknown == ("FORMAL_CHECK_PASS",)


def test_unknown_can_be_routed_to_review():
    result = evaluate_gate(
        "verification_success",
        [Criterion("FORMAL_CHECK_PASS", GateStatus.UNKNOWN)],
        fail_on_unknown=False,
    )
    assert result.status is GateStatus.REVIEW_REQUIRED


def test_review_required_is_not_clean_pass():
    result = evaluate_gate(
        "research_ready",
        [
            Criterion("EXPERT_REVIEW_PASS", GateStatus.REVIEW_REQUIRED),
            Criterion("PROVENANCE_COMPLETE", GateStatus.PASS),
        ],
    )
    assert result.status is GateStatus.REVIEW_REQUIRED
    assert result.review_required == ("EXPERT_REVIEW_PASS",)


def test_limitations_remain_machine_visible():
    result = evaluate_gate(
        "generalization_success",
        [
            Criterion("OUT_OF_SAMPLE_VALIDATION_PASS", GateStatus.PASS),
            Criterion("EXTERNAL_VALIDITY_DOCUMENTED", GateStatus.PASS_WITH_LIMITATIONS),
        ],
    )
    assert result.status is GateStatus.PASS_WITH_LIMITATIONS
    assert result.limitations == ("EXTERNAL_VALIDITY_DOCUMENTED",)


def test_all_not_applicable_is_not_a_pass():
    result = evaluate_gate(
        "statistical_validity_pass",
        [Criterion("STATISTICAL_CHECK", GateStatus.NOT_APPLICABLE)],
    )
    assert result.status is GateStatus.NOT_APPLICABLE


def test_canonical_discovery_gate_contains_core_controls():
    criteria = required_criteria("discovery_claim_ready")
    assert "RESEARCH_READY" in criteria
    assert "CLAIMS_MATCH_EVIDENCE" in criteria
    assert "INDEPENDENT_EXPERT_CONFIRMATION" in criteria
    assert "ARTIFACTS_ARCHIVED" in criteria


def test_provenance_tracks_human_and_ai_research_inputs():
    criteria = required_criteria("provenance_complete")
    assert "MODEL_VERSION_RECORDED" in criteria
    assert "SYSTEM_PROMPTS_RECORDED" in criteria
    assert "RETRIEVED_CONTEXT_RECORDED" in criteria
    assert "HUMAN_INTERVENTIONS_RECORDED" in criteria
    assert "ARTIFACT_HASHES_VERIFIED" in criteria

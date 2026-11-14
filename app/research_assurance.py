"""Scientific Discovery Assurance Framework for EvalForge.

The framework models research readiness as composable gates rather than a
single boolean. Each criterion can be PASS, PASS_WITH_LIMITATIONS,
REVIEW_REQUIRED, FAIL, NOT_APPLICABLE, or UNKNOWN. This prevents unknown or
non-applicable checks from being silently treated as successful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping


class GateStatus(str, Enum):
    PASS = "PASS"
    PASS_WITH_LIMITATIONS = "PASS_WITH_LIMITATIONS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Criterion:
    name: str
    status: GateStatus
    note: str | None = None


@dataclass(frozen=True)
class GateResult:
    name: str
    status: GateStatus
    criteria: tuple[Criterion, ...]
    failed: tuple[str, ...] = field(default_factory=tuple)
    review_required: tuple[str, ...] = field(default_factory=tuple)
    unknown: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)


FAIL_CLOSED_STATUSES = {GateStatus.FAIL, GateStatus.UNKNOWN}


def evaluate_gate(
    name: str,
    criteria: Iterable[Criterion],
    *,
    fail_on_unknown: bool = True,
) -> GateResult:
    """Evaluate a research assurance gate with conservative semantics.

    NOT_APPLICABLE checks are excluded from pass/fail aggregation. UNKNOWN
    fails closed by default. PASS_WITH_LIMITATIONS preserves a successful gate
    while making limitations machine-visible. REVIEW_REQUIRED never becomes a
    clean pass.
    """

    items = tuple(criteria)
    failed = tuple(c.name for c in items if c.status is GateStatus.FAIL)
    review = tuple(c.name for c in items if c.status is GateStatus.REVIEW_REQUIRED)
    unknown = tuple(c.name for c in items if c.status is GateStatus.UNKNOWN)
    limitations = tuple(c.name for c in items if c.status is GateStatus.PASS_WITH_LIMITATIONS)

    if failed or (fail_on_unknown and unknown):
        status = GateStatus.FAIL
    elif review or unknown:
        status = GateStatus.REVIEW_REQUIRED
    elif limitations:
        status = GateStatus.PASS_WITH_LIMITATIONS
    else:
        applicable = [c for c in items if c.status is not GateStatus.NOT_APPLICABLE]
        status = GateStatus.PASS if applicable else GateStatus.NOT_APPLICABLE

    return GateResult(
        name=name,
        status=status,
        criteria=items,
        failed=failed,
        review_required=review,
        unknown=unknown,
        limitations=limitations,
    )


GATES: Mapping[str, tuple[str, ...]] = {
    "problem_ready": (
        "PROBLEM_FORMALIZED",
        "SCOPE_DEFINED",
        "CLAIM_TYPE_DEFINED",
        "SUCCESS_CRITERIA_DEFINED",
        "FAILURE_CRITERIA_DEFINED",
        "ASSUMPTIONS_EXPLICIT",
        "BOUNDARY_CONDITIONS_DEFINED",
        "EVALUATION_PROTOCOL_PREDEFINED",
        "ACCEPTANCE_THRESHOLDS_DEFINED",
        "PROHIBITED_SHORTCUTS_DEFINED",
    ),
    "candidate_valid": (
        "PROBLEM_READY",
        "NOVEL_CANDIDATE",
        "CLAIMS_MACHINE_READABLE",
        "INTERNAL_CONSISTENCY_PASS",
        "EVIDENCE_TRACEABLE",
        "DERIVATION_TRACEABLE",
        "NO_UNRESOLVED_CRITICAL_ERROR",
        "CLAIM_SCOPE_WITHIN_ASSUMPTIONS",
    ),
    "falsification_pass": (
        "CANDIDATE_VALID",
        "ADVERSARIAL_REVIEW_PASS",
        "COUNTEREXAMPLE_SEARCH_PASS",
        "EDGE_CASE_SEARCH_PASS",
        "CONTRADICTION_SEARCH_PASS",
        "ASSUMPTION_VIOLATION_TEST_PASS",
        "PROPERTY_BASED_TEST_PASS",
        "METAMORPHIC_TEST_PASS",
        "NO_KNOWN_FATAL_COUNTEREXAMPLE",
    ),
    "statistical_validity_pass": (
        "SAMPLE_SIZE_JUSTIFIED",
        "EFFECT_SIZE_REPORTED",
        "CONFIDENCE_INTERVALS_REPORTED",
        "MULTIPLE_HYPOTHESIS_CONTROL_PASS",
        "TEST_ASSUMPTIONS_CHECKED",
        "MODEL_SELECTION_BIAS_CONTROLLED",
        "DATA_SNOOPING_CONTROLLED",
        "LEAKAGE_CHECK_PASS",
        "UNCERTAINTY_CALIBRATED",
        "NEGATIVE_RESULTS_RECORDED",
    ),
    "verification_success": (
        "FALSIFICATION_PASS",
        "INDEPENDENT_VERIFICATION_PASS",
        "FORMAL_CHECK_PASS",
        "SYMBOLIC_CHECK_PASS",
        "NUMERICAL_CHECK_PASS",
        "DIMENSIONAL_CONSISTENCY_PASS",
        "BASELINE_COMPARISON_PASS",
        "ROBUSTNESS_CHECK_PASS",
        "SENSITIVITY_ANALYSIS_PASS",
        "UNCERTAINTY_QUANTIFIED",
        "STATISTICAL_VALIDITY_PASS",
        "NO_KNOWN_CONTRADICTION",
    ),
    "generalization_success": (
        "VERIFICATION_SUCCESS",
        "OUT_OF_SAMPLE_VALIDATION_PASS",
        "HOLDOUT_INTEGRITY_PASS",
        "TEMPORAL_VALIDATION_PASS",
        "EXTERNAL_DATASET_VALIDATION_PASS",
        "DISTRIBUTION_SHIFT_TEST_PASS",
        "STRESS_TEST_PASS",
        "BOUNDARY_CONDITIONS_TESTED",
        "REGIME_ANALYSIS_PASS",
        "FAILURE_ENVELOPE_DEFINED",
        "EXTERNAL_VALIDITY_DOCUMENTED",
    ),
    "novelty_validated": (
        "GENERALIZATION_SUCCESS",
        "SYSTEMATIC_LITERATURE_SEARCH_PASS",
        "PRIOR_ART_CHECK_PASS",
        "DUPLICATION_CHECK_PASS",
        "CLOSEST_PRIOR_WORK_IDENTIFIED",
        "DELTA_OVER_PRIOR_WORK_EXPLICIT",
        "NOVELTY_CLAIM_CALIBRATED",
        "SOURCE_ATTRIBUTION_COMPLETE",
    ),
    "reproducibility_pass": (
        "NOVELTY_VALIDATED",
        "CODE_AVAILABLE",
        "DATA_AVAILABLE_OR_JUSTIFIED",
        "CONFIGURATION_CAPTURED",
        "DEPENDENCIES_PINNED",
        "ENVIRONMENT_REPRODUCIBLE",
        "RANDOM_SEEDS_RECORDED",
        "HARDWARE_REQUIREMENTS_RECORDED",
        "EXECUTION_INSTRUCTIONS_COMPLETE",
        "EXPECTED_OUTPUTS_DEFINED",
        "ARTIFACT_HASHES_VERIFIED",
        "CLEAN_ROOM_REPRODUCTION_PASS",
    ),
    "replication_pass": (
        "REPRODUCIBILITY_PASS",
        "INDEPENDENT_TEAM_USED",
        "INDEPENDENT_ENVIRONMENT_USED",
        "INDEPENDENT_IMPLEMENTATION_USED",
        "RESULTS_WITHIN_ACCEPTANCE_RANGE",
        "DISCREPANCIES_EXPLAINED",
        "INDEPENDENT_REPRODUCTION_PASS",
    ),
    "provenance_complete": (
        "DATA_LINEAGE_COMPLETE",
        "SOURCE_ATTRIBUTION_COMPLETE",
        "LICENSES_RECORDED",
        "DATA_ACQUISITION_TIME_RECORDED",
        "MODEL_PROVIDER_RECORDED",
        "MODEL_VERSION_RECORDED",
        "MODEL_CONFIGURATION_RECORDED",
        "SYSTEM_PROMPTS_RECORDED",
        "RESEARCH_PROTOCOL_RECORDED",
        "TOOL_CALLS_RECORDED",
        "RETRIEVED_CONTEXT_RECORDED",
        "EXTERNAL_API_RESPONSES_TRACED",
        "COMPUTE_ENVIRONMENT_RECORDED",
        "RANDOM_SEEDS_RECORDED",
        "HUMAN_INTERVENTIONS_RECORDED",
        "HUMAN_DECISIONS_ATTRIBUTED",
        "ARTIFACT_HASHES_VERIFIED",
        "TIMESTAMPS_RECORDED",
        "CHAIN_OF_CUSTODY_COMPLETE",
        "DECISION_LOG_COMPLETE",
    ),
    "provenance_integrity_pass": (
        "PROVENANCE_COMPLETE",
        "TRAIN_TEST_CONTAMINATION_CHECK_PASS",
        "BENCHMARK_CONTAMINATION_CHECK_PASS",
        "PRIVATE_DATA_USAGE_DECLARED",
        "UNPUBLISHED_SOURCE_USAGE_DECLARED",
        "RETRIEVAL_CONTAMINATION_CHECK_PASS",
        "DATA_LICENSE_COMPLIANCE_PASS",
        "ATTRIBUTION_CONFLICT_CHECK_PASS",
    ),
    "research_integrity_pass": (
        "PROVENANCE_INTEGRITY_PASS",
        "NO_DATA_FABRICATION",
        "NO_RESULT_FABRICATION",
        "NO_CHERRY_PICKING",
        "NO_HIDDEN_EXCLUSIONS",
        "NO_UNDISCLOSED_POST_HOC_HYPOTHESES",
        "NEGATIVE_RESULTS_PRESERVED",
        "CONFLICT_OF_INTEREST_RECORDED",
        "FUNDING_DISCLOSED",
        "AUTHORSHIP_ATTRIBUTION_COMPLETE",
        "AI_CONTRIBUTION_DISCLOSED",
        "LIMITATIONS_DOCUMENTED",
        "THREATS_TO_VALIDITY_DOCUMENTED",
    ),
    "responsible_research_pass": (
        "RESEARCH_INTEGRITY_PASS",
        "ETHICS_REQUIREMENT_EVALUATED",
        "SAFETY_REQUIREMENT_EVALUATED",
        "PRIVACY_REQUIREMENT_EVALUATED",
        "DUAL_USE_RISK_ASSESSED",
        "HUMAN_SUBJECTS_COMPLIANCE_PASS",
        "DATA_PROTECTION_PASS",
        "RISK_MITIGATIONS_DOCUMENTED",
    ),
    "research_ready": (
        "REPLICATION_PASS",
        "RESPONSIBLE_RESEARCH_PASS",
        "PROVENANCE_COMPLETE",
        "METHOD_TRACE_COMPLETE",
        "COMPUTE_TRACE_COMPLETE",
        "FAILURE_CASES_DOCUMENTED",
        "CLAIM_LIMITATIONS_DOCUMENTED",
        "EXPERT_REVIEW_PASS",
        "REVIEW_OBJECTIONS_RESOLVED",
        "OPEN_CRITICAL_ISSUES_ZERO",
    ),
    "discovery_claim_ready": (
        "RESEARCH_READY",
        "CLAIMS_MATCH_EVIDENCE",
        "CLAIM_SCOPE_NOT_OVERSTATED",
        "NOVELTY_CLAIM_SUPPORTED",
        "ATTRIBUTION_COMPLETE",
        "INDEPENDENT_EXPERT_CONFIRMATION",
        "REPRODUCTION_INSTRUCTIONS_COMPLETE",
        "PUBLICATION_PACKAGE_COMPLETE",
        "ARTIFACTS_ARCHIVED",
        "VERSION_PINNED",
        "IMMUTABLE_IDENTIFIER_READY",
    ),
    "post_publication_valid": (
        "DISCOVERY_CLAIM_READY",
        "EXTERNAL_REPLICATION_STATUS_TRACKED",
        "EXTERNAL_CRITIQUES_TRACKED",
        "NEW_COUNTEREVIDENCE_TRACKED",
        "ERRATA_PROCESS_DEFINED",
        "CORRECTION_PROCESS_DEFINED",
        "RETRACTION_CRITERIA_DEFINED",
        "CLAIM_VERSIONING_ENABLED",
        "ARTIFACT_VERSIONING_ENABLED",
        "CURRENT_EVIDENCE_STILL_SUPPORTS_CLAIM",
    ),
    "discovery_still_valid": (
        "POST_PUBLICATION_VALID",
        "NO_NEW_FATAL_COUNTEREXAMPLE",
        "NO_REPLICATION_FAILURE_UNRESOLVED",
        "NO_PROVENANCE_INTEGRITY_FAILURE",
        "NO_CRITICAL_FORMAL_VERIFICATION_FAILURE",
        "NO_RESEARCH_INTEGRITY_VIOLATION",
    ),
}


def required_criteria(gate_name: str) -> tuple[str, ...]:
    """Return the canonical criteria for a named assurance gate."""

    try:
        return GATES[gate_name]
    except KeyError as exc:
        raise ValueError(f"Unknown assurance gate: {gate_name}") from exc

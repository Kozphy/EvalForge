from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Severity = Literal["no_issue", "minor", "major"]
ClaimVerdict = Literal["supported", "contradicted", "unsupported", "uncertain", "not_verifiable"]
ExpectedLabelInput = Literal["pass", "no_issue", "minor", "major"]


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    REVIEWED = "REVIEWED"
    DISAGREEMENT = "DISAGREEMENT"
    ADJUDICATED = "ADJUDICATED"


def normalize_expected_label(value: str | None) -> Severity | None:
    if value is None or value == "":
        return None
    mapping = {
        "pass": "no_issue",
        "no_issue": "no_issue",
        "minor": "minor",
        "major": "major",
    }
    key = value.strip().casefold()
    if key not in mapping:
        raise ValueError("Expected one of: pass, no_issue, minor, major.")
    return mapping[key]  # type: ignore[return-value]


class RequirementSpec(BaseModel):
    exact_sentences: int | None = Field(default=None, ge=1, le=100)
    min_sentences: int | None = Field(default=None, ge=0, le=100)
    max_sentences: int | None = Field(default=None, ge=1, le=100)
    min_words: int | None = Field(default=None, ge=0, le=100_000)
    max_words: int | None = Field(default=None, ge=1, le=100_000)
    required_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    required_regex: list[str] = Field(default_factory=list)
    forbidden_regex: list[str] = Field(default_factory=list)
    require_json: bool = False
    json_schema: dict[str, Any] | None = None
    required_json_keys: list[str] = Field(default_factory=list)
    forbidden_json_keys: list[str] = Field(default_factory=list)
    exact_normalized_match: str | None = None
    require_date_format: bool = False
    require_email_format: bool = False
    require_url_format: bool = False
    require_citation: bool = False
    citation_ids: list[str] = Field(default_factory=list)
    require_python_syntax: bool = False
    require_sql_syntax: bool = False

    @model_validator(mode="after")
    def validate_bounds(self) -> RequirementSpec:
        if (
            self.min_sentences is not None
            and self.max_sentences is not None
            and self.min_sentences > self.max_sentences
        ):
            raise ValueError("min_sentences cannot exceed max_sentences")
        if (
            self.min_words is not None
            and self.max_words is not None
            and self.min_words > self.max_words
        ):
            raise ValueError("min_words cannot exceed max_words")
        for pattern in [*self.required_regex, *self.forbidden_regex]:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern: {pattern!r} ({exc})") from exc
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class EvalCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1)
    response: str = Field(min_length=1)
    expected_label: ExpectedLabelInput | None = None
    requirements: RequirementSpec = Field(default_factory=RequirementSpec)
    metadata: dict[str, Any] = Field(default_factory=dict)
    case_id: str | None = Field(default=None, max_length=120)

    @field_validator("expected_label", mode="before")
    @classmethod
    def _normalize_label(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        return normalize_expected_label(str(value))


class EvalCaseBatchCreate(BaseModel):
    cases: list[EvalCaseCreate] = Field(min_length=1, max_length=10_000)


class RunCreate(BaseModel):
    provider: Literal["heuristic", "openai"] = "heuristic"
    model: str = "gpt-5.6"
    top_k: int = Field(default=4, ge=1, le=12)
    prompt_version: str = "1"
    system_prompt: str | None = None
    grader_prompt: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=128_000)
    evidence_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    rule_set_version: str = "1"
    dataset_version: str | None = None
    model_version: str | None = None


class EvidenceItem(BaseModel):
    document_id: int
    title: str
    chunk_id: str
    text: str
    score: float = Field(ge=0, le=1)


class RuleFinding(BaseModel):
    """Structured deterministic finding.

    `rule` / `detail` are retained for MVP compatibility; prefer `rule_type` / `message`.
    """

    rule_type: str
    passed: bool
    severity: Severity
    expected: str | None = None
    observed: str | None = None
    message: str
    rule: str | None = None
    detail: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _compat_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if "rule_type" not in payload and "rule" in payload:
            payload["rule_type"] = payload["rule"]
        if "message" not in payload and "detail" in payload:
            payload["message"] = payload["detail"]
        if "rule" not in payload and "rule_type" in payload:
            payload["rule"] = payload["rule_type"]
        if "detail" not in payload and "message" in payload:
            payload["detail"] = payload["message"]
        return payload


class ClaimAssessment(BaseModel):
    claim: str
    verdict: ClaimVerdict
    confidence: float = Field(ge=0, le=1)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    reason: str


class GraderOutput(BaseModel):
    verdict: Literal["pass", "fail", "review"]
    severity: Severity
    score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    reason: str
    claims: list[ClaimAssessment] = Field(default_factory=list)
    needs_human_review: bool = False


class ImportErrorItem(BaseModel):
    row: int
    field: str | None = None
    code: str
    message: str


class ImportResult(BaseModel):
    filename: str
    dry_run: bool
    atomic: bool
    total_rows: int
    validated_rows: int
    imported_rows: int
    rejected_rows: int
    duplicate_rows: int
    errors: list[ImportErrorItem] = Field(default_factory=list)


class ReviewDecisionCreate(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    final_label: Severity
    comment: str | None = Field(default=None, max_length=4000)


class AdjudicationCreate(BaseModel):
    adjudicator: str = Field(min_length=1, max_length=120)
    final_label: Severity
    comment: str | None = Field(default=None, max_length=4000)

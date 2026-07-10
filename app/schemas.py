from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["no_issue", "minor", "major"]
ClaimVerdict = Literal["supported", "contradicted", "unsupported", "uncertain", "not_verifiable"]


class RequirementSpec(BaseModel):
    exact_sentences: int | None = Field(default=None, ge=1, le=100)
    max_sentences: int | None = Field(default=None, ge=1, le=100)
    max_words: int | None = Field(default=None, ge=1, le=100_000)
    required_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    require_json: bool = False


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
    expected_label: Severity | None = None
    requirements: RequirementSpec = Field(default_factory=RequirementSpec)
    metadata: dict = Field(default_factory=dict)


class EvalCaseBatchCreate(BaseModel):
    cases: list[EvalCaseCreate] = Field(min_length=1, max_length=10_000)


class RunCreate(BaseModel):
    provider: Literal["heuristic", "openai"] = "heuristic"
    model: str = "gpt-5.6"
    top_k: int = Field(default=4, ge=1, le=12)


class EvidenceItem(BaseModel):
    document_id: int
    title: str
    chunk_id: str
    text: str
    score: float = Field(ge=0, le=1)


class RuleFinding(BaseModel):
    rule: str
    passed: bool
    severity: Severity
    detail: str


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

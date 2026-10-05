"""Schemas for the finance evaluation vertical."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


Difficulty = Literal["easy", "medium", "hard"]
TaskCategory = Literal[
    "financial_statements",
    "journal_entries",
    "accounting_equations",
    "revenue_recognition",
    "expense_classification",
    "gross_margin",
    "cash_flow",
    "financial_ratios",
    "audit_reasoning",
    "internal_controls",
    "reconciliation",
    "anomaly_detection",
    "financial_analysis",
    "sql_financial",
    "python_financial",
]


class GradeMode(str, Enum):
    NUMERIC = "numeric"
    EXACT_TEXT = "exact_text"
    CONTAINS_ALL = "contains_all"
    JOURNAL_JSON = "journal_json"
    SQL_RESULT = "sql_result"
    PYTHON_RESULT = "python_result"
    MULTI_CHOICE = "multi_choice"


class GoldenAnswer(BaseModel):
    mode: GradeMode
    value: Any
    tolerance: float | None = None
    unit: str | None = None
    notes: str | None = None


class GradingRubric(BaseModel):
    correct_if: str
    partial_credit: str | None = None
    fail_if: str
    max_score: float = 1.0


class FinanceCase(BaseModel):
    case_id: str
    dataset_version: str
    category: TaskCategory
    difficulty: Difficulty
    question: str
    expected_answer: str
    structured_golden: GoldenAnswer
    grading_rubric: GradingRubric
    allowed_tolerance: float | None = None
    required_evidence: list[str] = Field(default_factory=list)
    known_failure_modes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Simulated candidate response for offline reproducible runs (not gold).
    candidate_response: str
    planted_failure: str = "FIN-NONE"
    split: Literal["dev", "test"] = "test"


class CaseResult(BaseModel):
    case_id: str
    category: str
    difficulty: str
    passed: bool
    score: float
    failure_codes: list[str] = Field(default_factory=list)
    deterministic_detail: dict[str, Any] = Field(default_factory=dict)
    judge: dict[str, Any] | None = None
    human_review: dict[str, Any] | None = None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost_usd: float | None = None


class RunMetrics(BaseModel):
    n_cases: int
    n_passed: int
    accuracy: float
    pass_rate: float
    hallucination_rate: float
    calculation_error_rate: float
    reasoning_error_rate: float
    citation_evidence_failure_rate: float
    instruction_following_failure_rate: float
    critical_error_rate: float
    mean_latency_ms: float | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    false_positive_rate: float | None = None
    accuracy_ci95: tuple[float, float] | None = None
    failure_counts: dict[str, int] = Field(default_factory=dict)


class PolicyOutcome(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class HumanRubricScores(BaseModel):
    correctness: int = Field(ge=1, le=5)
    reasoning: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    domain_validity: int = Field(ge=1, le=5)
    evidence_quality: int = Field(ge=1, le=5)
    financial_risk: Literal["low", "medium", "high", "critical"]
    severity: Literal["none", "low", "medium", "high", "critical"]
    decision: Literal["pass", "fail"]
    notes: str | None = None

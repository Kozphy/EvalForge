"""Canonical evaluation contracts (provider-neutral)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.control_plane import SCHEMA_VERSION


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class MetricCategory(str, Enum):
    QUALITY = "quality"
    RAG = "rag"
    AGENT = "agent"
    SECURITY = "security"
    OBSERVABILITY = "observability"
    CUSTOM = "custom"


class RunState(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    POLICY_REJECTED = "POLICY_REJECTED"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"
    WARN = "WARN"


class ReviewOutcome(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_RERUN = "REQUEST_RERUN"
    WAIVE_WITH_REASON = "WAIVE_WITH_REASON"


class FailureClass(str, Enum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DATASET_ERROR = "DATASET_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    EVALUATOR_ERROR = "EVALUATOR_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    NORMALIZATION_ERROR = "NORMALIZATION_ERROR"
    REGRESSION_FAILURE = "REGRESSION_FAILURE"
    POLICY_FAILURE = "POLICY_FAILURE"
    SECURITY_FAILURE = "SECURITY_FAILURE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    HUMAN_REJECTION = "HUMAN_REJECTION"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"


class EvaluationCase(BaseModel):
    case_id: str
    prompt: str
    response: str = ""
    expected_label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    requirements: dict[str, Any] = Field(default_factory=dict)


class EvaluatorDescriptor(BaseModel):
    name: str
    version: str | None = None
    category: MetricCategory = MetricCategory.CUSTOM
    optional: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationEvidence(BaseModel):
    schema_version: str = SCHEMA_VERSION
    payload: dict[str, Any] = Field(default_factory=dict)
    redacted: bool = False


class EvaluationArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: new_id("art"))
    kind: str
    uri: str | None = None
    content_type: str | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """Provider-neutral normalized evaluation result."""

    schema_version: str = SCHEMA_VERSION
    evaluation_id: str = Field(default_factory=lambda: new_id("eval"))
    run_id: str
    experiment_id: str

    evaluator_name: str
    evaluator_version: str | None = None

    metric_name: str
    metric_category: MetricCategory = MetricCategory.CUSTOM

    score: float | None = None
    passed: bool | None = None
    severity: str | None = None

    dataset_id: str | None = None
    case_id: str | None = None

    model: str | None = None
    model_version: str | None = None
    prompt_id: str | None = None
    prompt_version: str | None = None
    trace_id: str | None = None

    evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)

    failure_class: FailureClass | None = None
    failure_code: str | None = None
    retryable: bool = False
    message: str | None = None


class RawEvaluationResult(BaseModel):
    """Opaque provider payload before normalization."""

    evaluator_name: str
    case_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)


class EvaluationContext(BaseModel):
    experiment_id: str
    run_id: str
    dataset_id: str | None = None
    model: str | None = None
    model_version: str | None = None
    prompt_id: str | None = None
    prompt_version: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    tracing_enabled: bool = False
    trace_provider: str | None = None


class EvaluationRun(BaseModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    experiment_id: str
    state: RunState = RunState.PENDING
    attempt: int = 1
    retry_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    failure_class: FailureClass | None = None
    last_checkpoint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentCandidate(BaseModel):
    model: str | None = None
    model_version: str | None = None
    prompt: str | None = None
    prompt_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentBudget(BaseModel):
    max_cost_usd: float | None = None
    max_model_calls: int | None = None
    max_runtime_seconds: float | None = None


class ExperimentSpec(BaseModel):
    """Declarative experiment configuration (YAML/JSON compatible)."""

    schema_version: str = SCHEMA_VERSION
    experiment_id: str = Field(default_factory=lambda: new_id("exp"))
    name: str
    dataset_id: str
    cases: list[EvaluationCase] = Field(default_factory=list)
    candidate: ExperimentCandidate = Field(default_factory=ExperimentCandidate)
    baseline_ref: str | None = None
    evaluators: list[str] = Field(default_factory=list)
    policy_name: str | None = None
    budget: ExperimentBudget = Field(default_factory=ExperimentBudget)
    tracing_provider: str | None = None
    tracing_enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class HealthStatus(BaseModel):
    name: str
    healthy: bool
    detail: str = ""
    version: str | None = None

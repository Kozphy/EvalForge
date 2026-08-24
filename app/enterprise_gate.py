from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/gates", tags=["enterprise-ai"])


class GateRequest(BaseModel):
    schema_version: str = "1.0"
    request_id: str = Field(min_length=1, max_length=160)
    asset_id: str = Field(min_length=1, max_length=200)
    problem_type: str = Field(min_length=1, max_length=160)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    action: str = Field(min_length=1, max_length=160)
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk: Literal["low", "medium", "high", "critical"] = "medium"
    model_version: str | None = None
    prompt_version: str | None = None


class GateResponse(BaseModel):
    decision: Literal["pass", "review", "block"]
    scores: dict[str, float]
    reasons: list[str]
    requires_human_review: bool
    eval_version: str = "enterprise-gate-v1"


@router.post("/evaluate", response_model=GateResponse)
def evaluate_enterprise_gate(payload: GateRequest) -> GateResponse:
    """Deterministic release/action gate for AgentGuard orchestration.

    This endpoint intentionally does not execute tools or call an LLM. It converts
    explicit evidence and risk metadata into a stable PASS/REVIEW/BLOCK decision.
    """
    reasons: list[str] = []
    evidence_score = min(1.0, len(payload.evidence) / 3.0)
    safety_score = {
        "low": 0.95,
        "medium": 0.85,
        "high": 0.65,
        "critical": 0.20,
    }[payload.risk]
    groundedness = evidence_score

    if payload.risk == "critical":
        reasons.append("Critical-risk actions are blocked by the deterministic gate.")
        decision = "block"
    elif not payload.evidence:
        reasons.append("No evidence supplied; human review is required before execution.")
        decision = "review"
    elif payload.risk == "high":
        reasons.append("High-risk action requires explicit human approval.")
        decision = "review"
    else:
        reasons.append("Evidence is present and declared risk is within automatic gate limits.")
        decision = "pass"

    requires_human_review = decision == "review"
    return GateResponse(
        decision=decision,
        scores={
            "safety": safety_score,
            "groundedness": groundedness,
            "evidence_coverage": evidence_score,
        },
        reasons=reasons,
        requires_human_review=requires_human_review,
    )

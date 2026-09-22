"""Human review models for control-plane approval."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.control_plane.contracts import ReviewOutcome, new_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewRequest(BaseModel):
    review_id: str = Field(default_factory=lambda: new_id("rev"))
    experiment_id: str
    run_id: str
    reason: str
    created_at: datetime = Field(default_factory=utc_now)


class ReviewerComment(BaseModel):
    reviewer: str
    comment: str
    created_at: datetime = Field(default_factory=utc_now)


class ReviewDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: new_id("rdec"))
    review_id: str
    reviewer: str
    outcome: ReviewOutcome
    comment: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalEvidence(BaseModel):
    experiment_id: str
    run_id: str
    decisions: list[ReviewDecision] = Field(default_factory=list)

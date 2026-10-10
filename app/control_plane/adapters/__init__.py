"""Adapter protocol and shared types."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.control_plane.contracts import (
    EvaluationCase,
    EvaluationContext,
    EvaluationResult,
    HealthStatus,
    RawEvaluationResult,
)


@runtime_checkable
class EvaluatorAdapter(Protocol):
    @property
    def name(self) -> str: ...

    def healthcheck(self) -> HealthStatus: ...

    def prepare(self, context: EvaluationContext) -> None: ...

    def execute(
        self,
        cases: list[EvaluationCase],
        context: EvaluationContext,
    ) -> list[RawEvaluationResult]: ...

    def normalize(self, raw_result: RawEvaluationResult) -> EvaluationResult: ...


@runtime_checkable
class TraceProvider(Protocol):
    @property
    def name(self) -> str: ...

    def healthcheck(self) -> HealthStatus: ...

    def fetch_trace(self, trace_id: str) -> dict: ...

    def link_trace(self, run_id: str, trace_id: str) -> None: ...

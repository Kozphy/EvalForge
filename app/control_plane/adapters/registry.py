"""Evaluator registry — discovery without hard-coding providers into orchestration."""

from __future__ import annotations

from app.control_plane.adapters import EvaluatorAdapter
from app.control_plane.contracts import HealthStatus


class EvaluatorRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, EvaluatorAdapter] = {}

    def register(self, adapter: EvaluatorAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        self._adapters.pop(name, None)

    def discover(self) -> list[str]:
        """Return registered names (explicit registration today; entry-points later)."""
        return sorted(self._adapters)

    def list(self) -> list[str]:
        return self.discover()

    def get(self, name: str) -> EvaluatorAdapter:
        if name not in self._adapters:
            raise KeyError(f"Evaluator not registered: {name}")
        return self._adapters[name]

    def healthcheck(self) -> list[HealthStatus]:
        return [adapter.healthcheck() for adapter in self._adapters.values()]


def build_default_registry(*, include_optional: bool = True) -> EvaluatorRegistry:
    """Register first-party and optional adapters. Missing deps degrade gracefully."""
    from app.control_plane.adapters.custom.heuristic import HeuristicAdapter
    from app.control_plane.adapters.deepeval.adapter import DeepEvalAdapter
    from app.control_plane.adapters.promptfoo.adapter import PromptfooAdapter

    registry = EvaluatorRegistry()
    registry.register(HeuristicAdapter())
    if include_optional:
        registry.register(DeepEvalAdapter())
        registry.register(PromptfooAdapter())
    return registry

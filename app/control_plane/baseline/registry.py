"""Baseline registry — immutable versions; promotion creates a new version."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.control_plane.contracts import new_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Baseline(BaseModel):
    baseline_id: str = Field(default_factory=lambda: new_id("bl"))
    name: str
    version: int = 1
    dataset_id: str
    candidate: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    source_experiment_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InMemoryBaselineRegistry:
    def __init__(self) -> None:
        self._items: list[Baseline] = []

    def create(self, baseline: Baseline) -> Baseline:
        # Immutability: never mutate existing; new creates are append-only.
        for item in self._items:
            if item.name == baseline.name and item.active:
                item.active = False
        self._items.append(baseline)
        return baseline

    def promote(
        self,
        *,
        name: str,
        dataset_id: str,
        candidate: dict[str, Any],
        metrics: dict[str, float],
        experiment_id: str | None = None,
    ) -> Baseline:
        prior = [b for b in self._items if b.name == name]
        version = (max(b.version for b in prior) + 1) if prior else 1
        return self.create(
            Baseline(
                name=name,
                version=version,
                dataset_id=dataset_id,
                candidate=candidate,
                metrics=metrics,
                source_experiment_id=experiment_id,
            )
        )

    def list(self, name: str | None = None) -> list[Baseline]:
        items = self._items
        if name:
            items = [b for b in items if b.name == name]
        return sorted(items, key=lambda b: (b.name, b.version))

    def get_active(self, name: str) -> Baseline | None:
        for item in reversed(self._items):
            if item.name == name and item.active:
                return item
        return None

    def rollback_metadata(self, name: str, version: int) -> Baseline:
        """Mark a prior version active without mutating its metrics payload."""
        target = None
        for item in self._items:
            if item.name == name:
                item.active = item.version == version
                if item.version == version:
                    target = item
        if target is None:
            raise KeyError(f"Baseline {name}@v{version} not found")
        return target

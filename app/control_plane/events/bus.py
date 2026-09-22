"""Simple in-process domain event bus."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DomainEvent:
    name: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)


class InProcessEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[DomainEvent], None]]] = defaultdict(list)
        self.history: list[DomainEvent] = []

    def subscribe(self, name: str, handler: Callable[[DomainEvent], None]) -> None:
        self._handlers[name].append(handler)

    def publish(self, name: str, payload: dict[str, Any]) -> DomainEvent:
        event = DomainEvent(name=name, payload=payload)
        self.history.append(event)
        for handler in self._handlers.get(name, []):
            handler(event)
        return event

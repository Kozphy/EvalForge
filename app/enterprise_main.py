"""EvalForge application entrypoint with Enterprise AI gate routes enabled."""

from __future__ import annotations

from .enterprise_gate import router as enterprise_gate_router
from .main import app

app.include_router(enterprise_gate_router)

__all__ = ["app"]

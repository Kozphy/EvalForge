"""Optional Phoenix trace provider — not mandatory."""

from __future__ import annotations

from app.control_plane.contracts import HealthStatus


def _phoenix_available() -> bool:
    try:
        import phoenix  # noqa: F401

        return True
    except ImportError:
        return False


class PhoenixTraceProvider:
    name = "phoenix"

    def healthcheck(self) -> HealthStatus:
        if not _phoenix_available():
            return HealthStatus(
                name=self.name,
                healthy=False,
                detail="phoenix package not installed (optional)",
            )
        return HealthStatus(name=self.name, healthy=True, detail="phoenix importable")

    def fetch_trace(self, trace_id: str) -> dict:
        if not _phoenix_available():
            return {"trace_id": trace_id, "error": "phoenix not installed", "spans": []}
        return {"trace_id": trace_id, "spans": [], "note": "live fetch not configured"}

    def link_trace(self, run_id: str, trace_id: str) -> None:
        return None


class FakePhoenixTraceProvider:
    name = "phoenix"

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(name=self.name, healthy=True, detail="fake", version="fake-1")

    def fetch_trace(self, trace_id: str) -> dict:
        return {
            "trace_id": trace_id,
            "spans": [
                {"span_id": "span-1", "kind": "model_call", "latency_ms": 42, "tokens": 100},
                {"span_id": "span-2", "kind": "retrieval", "latency_ms": 12},
            ],
        }

    def link_trace(self, run_id: str, trace_id: str) -> None:
        return None

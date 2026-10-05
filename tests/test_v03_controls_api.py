from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app


def _client(tmp_path: Path) -> TestClient:
    """Create an isolated TestClient backed by a fresh temporary database.

    Initialises a new SQLite database at tmp_path/test-v03.db and points
    the application at it so tests do not share state.

    Args:
        tmp_path: pytest temporary directory fixture path.

    Returns:
        TestClient wrapping the FastAPI app with the isolated database.
    """
    db.DB_PATH = tmp_path / "test-v03.db"
    db.init_db()
    return TestClient(app)


def test_run_persists_controls_and_trace(tmp_path: Path) -> None:
    """A heuristic run persists control reports and emits trace events.

    End-to-end test that:
    - Creates a project and seeds it with the demo fixture cases.
    - Executes a heuristic run with trace_enabled=True.
    - Asserts run metrics include allow/review/block counts.
    - Asserts every result in the payload carries a controls object.
    - Asserts GET /api/runs/{id}/controls returns per-result control data.
    - Asserts GET /api/runs/{id}/trace contains run, retrieval, grader,
      and controls stages.

    Args:
        tmp_path: pytest temporary directory fixture path.
    """
    with _client(tmp_path) as client:
        project = client.post(
            "/api/projects",
            json={"name": "Controls", "description": "v0.3"},
        )
        assert project.status_code == 201
        project_id = project.json()["id"]

        seeded = client.post(f"/api/projects/{project_id}/seed", json={})
        assert seeded.status_code == 201

        run = client.post(
            f"/api/projects/{project_id}/runs",
            json={
                "provider": "heuristic",
                "model": "offline",
                "top_k": 3,
                "trace_enabled": True,
            },
        )
        assert run.status_code == 201, run.text
        payload = run.json()
        run_id = payload["id"]

        assert payload["metrics"]["controls"]["allow_count"] >= 0
        assert payload["metrics"]["controls"]["review_count"] >= 0
        assert payload["metrics"]["controls"]["block_count"] >= 0
        assert all("controls" in result for result in payload["results"])

        controls = client.get(f"/api/runs/{run_id}/controls")
        assert controls.status_code == 200
        assert len(controls.json()["results"]) == 3

        trace = client.get(f"/api/runs/{run_id}/trace")
        assert trace.status_code == 200
        stages = {item["stage"] for item in trace.json()}
        assert {"run", "retrieval", "grader", "controls"}.issubset(stages)

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app


def _client(tmp_path: Path) -> TestClient:
    db.DB_PATH = tmp_path / "test-v03.db"
    db.init_db()
    return TestClient(app)


def test_run_persists_controls_and_trace(tmp_path: Path) -> None:
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

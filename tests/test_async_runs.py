from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app


def _client(tmp_path: Path) -> TestClient:
    db.DB_PATH = tmp_path / "test-async.db"
    db.init_db()
    return TestClient(app)


def test_async_run_completes_and_links_run(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/projects", json={"name": "Async demo"})
        assert project.status_code == 201
        project_id = project.json()["id"]
        assert client.post(f"/api/projects/{project_id}/seed", json={}).status_code == 201

        queued = client.post(
            f"/api/projects/{project_id}/runs/async",
            json={"provider": "heuristic", "model": "offline", "top_k": 3},
        )
        assert queued.status_code == 202, queued.text
        job_id = queued.json()["id"]

        job = client.get(f"/api/run-jobs/{job_id}")
        assert job.status_code == 200
        payload = job.json()
        assert payload["status"] == "completed"
        assert payload["attempt_count"] == 1
        assert payload["run_id"] is not None
        assert payload["run"]["status"] == "completed"
        assert payload["run"]["metrics"]["case_count"] == 3


def test_async_run_requires_cases(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/projects", json={"name": "Empty"})
        project_id = project.json()["id"]

        response = client.post(
            f"/api/projects/{project_id}/runs/async",
            json={"provider": "heuristic", "model": "offline"},
        )
        assert response.status_code == 400
        assert "at least one evaluation case" in response.json()["detail"]


def test_async_jobs_can_be_filtered(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project = client.post("/api/projects", json={"name": "Filter demo"})
        project_id = project.json()["id"]
        client.post(f"/api/projects/{project_id}/seed", json={})
        client.post(
            f"/api/projects/{project_id}/runs/async",
            json={"provider": "heuristic", "model": "offline"},
        )

        response = client.get(
            "/api/run-jobs",
            params={"project_id": project_id, "status": "completed"},
        )
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["project_id"] == project_id
        assert jobs[0]["status"] == "completed"

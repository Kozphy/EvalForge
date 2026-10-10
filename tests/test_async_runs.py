from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.async_runs import enqueue_job, ensure_async_job_schema
from app.main import app
from app.schemas import RunCreate


def _client(tmp_path: Path) -> TestClient:
    db.DB_PATH = tmp_path / "test-async.db"
    db.init_db()
    ensure_async_job_schema()
    return TestClient(app)


def _seed_project(client: TestClient) -> int:
    """Create a project seeded with cases and return its id."""
    project = client.post("/api/projects", json={"name": "Test project"})
    assert project.status_code == 201
    project_id = project.json()["id"]
    assert client.post(f"/api/projects/{project_id}/seed", json={}).status_code == 201
    return project_id


def _enqueue_queued_job(project_id: int) -> int:
    """Insert a job in 'queued' state without triggering background processing."""
    config = RunCreate(provider="heuristic", model="offline")
    job = enqueue_job(project_id, config)
    return int(job["id"])


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


def test_cancel_queued_job_returns_cancelled(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _seed_project(client)
        job_id = _enqueue_queued_job(project_id)

        response = client.post(f"/api/run-jobs/{job_id}/cancel")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "cancelled"
        assert payload["cancel_requested"] is True


def test_cancel_completed_job_returns_409(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _seed_project(client)

        # Enqueue and let it run to completion via the API endpoint
        queued = client.post(
            f"/api/projects/{project_id}/runs/async",
            json={"provider": "heuristic", "model": "offline"},
        )
        assert queued.status_code == 202
        job_id = queued.json()["id"]

        # Verify it completed
        assert client.get(f"/api/run-jobs/{job_id}").json()["status"] == "completed"

        # Attempting to cancel a completed job must return 409
        response = client.post(f"/api/run-jobs/{job_id}/cancel")
        assert response.status_code == 409


def test_retry_cancelled_job_requeues_and_completes(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _seed_project(client)
        job_id = _enqueue_queued_job(project_id)

        # Cancel the queued job
        cancel_resp = client.post(f"/api/run-jobs/{job_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

        # Retry — background task runs synchronously in TestClient
        retry_resp = client.post(f"/api/run-jobs/{job_id}/retry")
        assert retry_resp.status_code == 202, retry_resp.text

        # Job should now be completed
        job = client.get(f"/api/run-jobs/{job_id}").json()
        assert job["status"] == "completed"
        assert job["run_id"] is not None


def test_get_unknown_job_returns_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/run-jobs/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

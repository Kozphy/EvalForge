from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app


def test_project_seed_and_run(tmp_path: Path) -> None:
    db.DB_PATH = tmp_path / "test.db"
    db.init_db()
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Demo", "description": "Test"})
        assert project.status_code == 201
        project_id = project.json()["id"]

        seeded = client.post(f"/api/projects/{project_id}/seed", json={})
        assert seeded.status_code == 201

        run = client.post(
            f"/api/projects/{project_id}/runs",
            json={"provider": "heuristic", "model": "offline", "top_k": 3},
        )
        assert run.status_code == 201, run.text
        payload = run.json()
        assert payload["status"] == "completed"
        assert len(payload["results"]) == 3
        assert payload["metrics"]["case_count"] == 3

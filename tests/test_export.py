from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app


def _client(tmp_path: Path) -> TestClient:
    db.DB_PATH = tmp_path / "export.db"
    db.init_db()
    return TestClient(app)


def _seeded_run(client: TestClient) -> tuple[int, int]:
    project_id = client.post("/api/projects", json={"name": "Export", "description": ""}).json()["id"]
    assert client.post(f"/api/projects/{project_id}/seed").status_code == 201
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={"provider": "heuristic", "model": "offline", "top_k": 3},
    )
    assert run.status_code == 201
    return project_id, run.json()["id"]


def test_export_formats_and_headers(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _, run_id = _seeded_run(client)
        json_resp = client.get(f"/api/runs/{run_id}/export?format=json")
        assert json_resp.status_code == 200
        assert "application/json" in json_resp.headers["content-type"]
        assert f"evalforge-run-{run_id}.json" in json_resp.headers["content-disposition"]
        payload = json_resp.json()
        assert payload["run_id"] == run_id
        assert "config" in payload
        assert len(payload["results"]) == 3

        jsonl_resp = client.get(f"/api/runs/{run_id}/export?format=jsonl")
        assert jsonl_resp.status_code == 200
        assert "application/x-ndjson" in jsonl_resp.headers["content-type"]
        lines = [line for line in jsonl_resp.text.splitlines() if line.strip()]
        assert len(lines) == 3

        csv_resp = client.get(f"/api/runs/{run_id}/export?format=csv")
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.headers["content-type"]
        assert "predicted_label" in csv_resp.text


def test_export_filters(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _, run_id = _seeded_run(client)
        review = client.get(f"/api/runs/{run_id}/export?format=jsonl&review_required=true")
        assert review.status_code == 200
        major = client.get(f"/api/runs/{run_id}/export?format=csv&predicted_label=major")
        assert major.status_code == 200
        incorrect = client.get(f"/api/runs/{run_id}/export?format=jsonl&incorrect_only=true")
        assert incorrect.status_code == 200
        assert incorrect.text.count("\n") >= 1 or incorrect.text == ""


def test_export_empty_and_missing(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = client.post("/api/projects", json={"name": "Empty", "description": ""}).json()["id"]
        # Create a completed run with no cases is impossible via API; missing run:
        missing = client.get("/api/runs/9999/export?format=json")
        assert missing.status_code == 404

        client.post(
            f"/api/projects/{project_id}/cases",
            json={"name": "solo", "prompt": "p", "response": "one word", "expected_label": "major", "requirements": {"max_words": 1}},
        )
        run = client.post(
            f"/api/projects/{project_id}/runs",
            json={"provider": "heuristic", "model": "offline"},
        ).json()
        # Filter that matches nothing
        empty = client.get(f"/api/runs/{run['id']}/export?format=jsonl&predicted_label=no_issue")
        assert empty.status_code == 200
        assert empty.text == ""

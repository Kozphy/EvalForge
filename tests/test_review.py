from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app


def _client(tmp_path: Path) -> TestClient:
    db.DB_PATH = tmp_path / "review.db"
    db.init_db()
    return TestClient(app)


def _reviewable_result(client: TestClient) -> int:
    project_id = client.post("/api/projects", json={"name": "Review", "description": ""}).json()["id"]
    client.post(
        f"/api/projects/{project_id}/cases",
        json={
            "name": "unsupported claim",
            "prompt": "Explain a scientific claim.",
            "response": "A newly invented planet has twelve purple moons.",
            "expected_label": "minor",
        },
    )
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={"provider": "heuristic", "model": "offline"},
    ).json()
    reviewable = [item for item in run["results"] if item["needs_human_review"]]
    assert reviewable
    return reviewable[0]["id"]


def test_review_queue_and_filters(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        result_id = _reviewable_result(client)
        queue = client.get("/api/reviews")
        assert queue.status_code == 200
        assert any(item["id"] == result_id for item in queue.json())

        filtered = client.get("/api/reviews?review_status=PENDING&sort_by=confidence&sort_dir=asc")
        assert filtered.status_code == 200


def test_review_decisions_disagreement_and_adjudication(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        result_id = _reviewable_result(client)
        first = client.post(
            f"/api/reviews/{result_id}/decisions",
            json={"reviewer": "alice", "final_label": "minor", "comment": "needs nuance"},
        )
        assert first.status_code == 201
        assert first.json()["review_status"] == "REVIEWED"

        second_agree = client.post(
            f"/api/reviews/{result_id}/decisions",
            json={"reviewer": "bob", "final_label": "minor", "comment": "agree"},
        )
        assert second_agree.status_code == 201
        assert second_agree.json()["review_status"] == "REVIEWED"

        # Update bob to disagree — preserves alice decision
        disagree = client.post(
            f"/api/reviews/{result_id}/decisions",
            json={"reviewer": "bob", "final_label": "major", "comment": "changed mind"},
        )
        assert disagree.status_code == 201
        body = disagree.json()
        assert body["review_status"] == "DISAGREEMENT"
        assert len(body["decisions"]) == 2

        adjudicated = client.post(
            f"/api/reviews/{result_id}/adjudicate",
            json={"adjudicator": "carol", "final_label": "minor", "comment": "final"},
        )
        assert adjudicated.status_code == 201
        assert adjudicated.json()["review_status"] == "ADJUDICATED"
        assert adjudicated.json()["final_label"] == "minor"
        assert len(adjudicated.json()["decisions"]) == 3


def test_invalid_label_and_missing_result(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        result_id = _reviewable_result(client)
        bad = client.post(
            f"/api/reviews/{result_id}/decisions",
            json={"reviewer": "alice", "final_label": "pass"},
        )
        assert bad.status_code == 422

        missing = client.get("/api/reviews/99999")
        assert missing.status_code == 404

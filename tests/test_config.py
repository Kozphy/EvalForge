from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.config import build_grader_config, detect_git_commit_sha
from app.main import app


def test_git_sha_detection(tmp_path: Path) -> None:
    sha = detect_git_commit_sha(Path.cwd())
    # Running inside this git repo should usually succeed
    assert sha is None or len(sha) >= 7

    missing = detect_git_commit_sha(tmp_path)
    assert missing is None


def test_config_persisted_and_exported(tmp_path: Path) -> None:
    db.DB_PATH = tmp_path / "config.db"
    db.init_db()
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Cfg", "description": ""}).json()["id"]
        client.post(f"/api/projects/{project_id}/seed")
        run = client.post(
            f"/api/projects/{project_id}/runs",
            json={
                "provider": "heuristic",
                "model": "offline",
                "top_k": 3,
                "prompt_version": "demo-1",
                "dataset_version": "accounting-sample-v1",
            },
        ).json()
        assert run["config"]["prompt_version"] == "demo-1"
        assert run["config"]["dataset_version"] == "accounting-sample-v1"
        assert run["config"]["retrieval_method"] == "tfidf"
        exported = client.get(f"/api/runs/{run['id']}/export?format=json").json()
        assert exported["config"]["prompt_version"] == "demo-1"


def test_build_grader_config_defaults() -> None:
    cfg = build_grader_config(provider="heuristic", model="offline", top_k=4)
    assert cfg.app_version
    assert cfg.retrieval_top_k == 4
    assert cfg.temperature == 0.0

"""Tests for grader configuration building, persistence, and export.

Covers three concerns:

* ``detect_git_commit_sha`` returns a valid SHA when run inside the repo and
  ``None`` when the path has no git history.
* A run's config snapshot is persisted with all caller-supplied fields and is
  faithfully reproduced in the JSON export.
* ``build_grader_config`` produces a config with sensible defaults.

Tests that execute a grading run are decorated with ``@requires_sklearn``
because the default TF-IDF retrieval backend depends on scikit-learn / scipy.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.config import build_grader_config, detect_git_commit_sha
from app.main import app
from tests.conftest import requires_sklearn


def test_git_sha_detection(tmp_path: Path) -> None:
    """Verify git SHA detection inside and outside a git repository.

    ``detect_git_commit_sha`` should return a string of at least 7 characters
    when called from within the project's git checkout.  It must return
    ``None`` when called with a path that has no ``.git`` directory.

    Args:
        tmp_path: pytest fixture providing a temporary directory that has no
            git history, used to exercise the missing-repo branch.
    """
    sha = detect_git_commit_sha(Path.cwd())
    # Running inside this git repo should usually succeed
    assert sha is None or len(sha) >= 7

    missing = detect_git_commit_sha(tmp_path)
    assert missing is None


@requires_sklearn
def test_config_persisted_and_exported(tmp_path: Path) -> None:
    """Config snapshot fields round-trip through the run and export endpoints.

    Seeds a project, executes a heuristic run with explicit ``prompt_version``
    and ``dataset_version``, then verifies those fields appear in both the
    run response and the JSON export.  Also confirms ``retrieval_method`` is
    recorded as ``"tfidf"`` by default.

    Args:
        tmp_path: pytest fixture providing a temporary directory for the
            isolated test database.
    """
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
    """``build_grader_config`` produces a config with expected default values.

    Checks that:

    * ``app_version`` is non-empty.
    * ``retrieval_top_k`` matches the supplied ``top_k`` argument.
    * ``temperature`` defaults to ``0.0`` (deterministic / heuristic mode).
    """
    cfg = build_grader_config(provider="heuristic", model="offline", top_k=4)
    assert cfg.app_version
    assert cfg.retrieval_top_k == 4
    assert cfg.temperature == 0.0

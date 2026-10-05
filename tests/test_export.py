"""Tests for the run export endpoint (``GET /api/runs/{id}/export``).

Covers three areas:

* All three formats (JSON, JSONL, CSV) return the correct status code,
  ``Content-Type`` header, ``Content-Disposition`` filename, and result count.
* Query-string filters (``review_required``, ``predicted_label``,
  ``incorrect_only``) are accepted and return HTTP 200.
* Edge cases: missing run → 404; filter with no matches → 200 with empty body.

Tests that seed a project and execute a grading run are decorated with
``@requires_sklearn`` because the default TF-IDF retrieval backend depends on
scikit-learn / scipy.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app
from tests.conftest import requires_sklearn


def _client(tmp_path: Path) -> TestClient:
    """Create a ``TestClient`` backed by a fresh, isolated SQLite database.

    Args:
        tmp_path: pytest-provided temporary directory; the database file is
            written here so each test starts with an empty schema.

    Returns:
        A configured :class:`~fastapi.testclient.TestClient` ready to make
        requests against the EvalForge app.
    """
    db.DB_PATH = tmp_path / "export.db"
    db.init_db()
    return TestClient(app)


def _seeded_run(client: TestClient) -> tuple[int, int]:
    """Seed a project and execute a heuristic run, returning their IDs.

    Creates a project named ``"Export"``, loads the built-in sample benchmark
    via the ``/seed`` endpoint, then runs the heuristic grader with
    ``top_k=3``.

    Args:
        client: An active :class:`~fastapi.testclient.TestClient` with an
            initialised database.

    Returns:
        A ``(project_id, run_id)`` tuple for use in export assertions.
    """
    project_id = client.post("/api/projects", json={"name": "Export", "description": ""}).json()["id"]
    assert client.post(f"/api/projects/{project_id}/seed").status_code == 201
    run = client.post(
        f"/api/projects/{project_id}/runs",
        json={"provider": "heuristic", "model": "offline", "top_k": 3},
    )
    assert run.status_code == 201
    return project_id, run.json()["id"]


@requires_sklearn
def test_export_formats_and_headers(tmp_path: Path) -> None:
    """All three export formats return correct headers and result counts.

    Verifies for each of ``json``, ``jsonl``, and ``csv``:

    * HTTP 200 status code.
    * ``Content-Type`` header matches the format.
    * JSON export: ``Content-Disposition`` contains the expected filename,
      payload has ``run_id`` and ``config`` keys, and ``results`` length is 3.
    * JSONL export: exactly 3 non-empty lines.
    * CSV export: ``predicted_label`` column is present.

    Args:
        tmp_path: pytest fixture providing a temporary directory for the
            isolated test database.
    """
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


@requires_sklearn
def test_export_filters(tmp_path: Path) -> None:
    """Export query-string filters are accepted and return HTTP 200.

    Exercises ``review_required=true``, ``predicted_label=major``, and
    ``incorrect_only=true`` on a completed run.  The test does not assert on
    result counts because filter outcomes depend on the sample-data labels;
    it only confirms the endpoint does not error.

    Args:
        tmp_path: pytest fixture providing a temporary directory for the
            isolated test database.
    """
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
    """Edge cases: missing run returns 404; unmatched filter returns empty body.

    Verifies that:

    * ``GET /api/runs/9999/export`` returns HTTP 404 when no run with that ID
      exists.
    * Exporting with a ``predicted_label`` filter that matches no results
      returns HTTP 200 with an empty response body.

    Args:
        tmp_path: pytest fixture providing a temporary directory for the
            isolated test database.
    """
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

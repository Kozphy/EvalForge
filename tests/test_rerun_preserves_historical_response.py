"""Regression tests: historical run responses must survive later reruns.

Executing a second client API run for the same case previously overwrote the
response shown and exported for the first run, because results were joined to
the mutable ``eval_cases.response`` column. The evaluated response is now
snapshotted onto each result row, so run details and exports stay stable while
the current case still tracks the latest response.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app import db
from app.main import app

ORIGINAL_RESPONSE = "Original answer X."
REPLACEMENT_RESPONSE = "Replacement answer Y."


def _client(tmp_path: Path) -> TestClient:
    """Build a test client backed by an isolated SQLite database.

    Args:
        tmp_path: Pytest temporary directory for the database file.

    Returns:
        Test client wired to the isolated application database.
    """
    db.DB_PATH = tmp_path / "rerun.db"
    db.init_db()
    return TestClient(app)


def _api_target() -> dict:
    """Return a valid client API target configuration for tests."""
    return {
        "url": "https://api.example.com/v1/generate",
        "body_template": '{"input": "{{prompt}}"}',
        "response_field_path": "data.answer",
        "timeout_seconds": 5.0,
    }


def _create_case(client: TestClient, project_id: int) -> None:
    """Add a single evaluation case to a project.

    Args:
        client: Test client for the application API.
        project_id: Identifier of the project receiving the case.
    """
    resp = client.post(
        f"/api/projects/{project_id}/cases",
        json={
            "name": "case-0",
            "prompt": "Prompt number 0",
            "response": "placeholder",
            "expected_label": "no_issue",
        },
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize(
    "variant",
    ["detail", "export-json", "export-jsonl", "export-csv"],
)
def test_rerun_preserves_historical_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
) -> None:
    """Regression-test that reruns never rewrite historical responses.

    Args:
        tmp_path: Isolated pytest temporary directory for the database.
        monkeypatch: Pytest fixture used to patch the HTTP client factory.
        variant: Endpoint under test: detail, export-json, export-jsonl,
            or export-csv.
    """
    answers = [ORIGINAL_RESPONSE, REPLACEMENT_RESPONSE]

    def handler(_request: httpx.Request) -> httpx.Response:
        answer = answers.pop(0) if answers else ""
        return httpx.Response(200, json={"data": {"answer": answer}})

    def build_client(timeout_seconds: float = 30.0) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    with _client(tmp_path) as client:
        project_id = client.post(
            "/api/projects",
            json={"name": "Rerun", "description": "historical responses"},
        ).json()["id"]
        _create_case(client, project_id)
        target = client.put(
            f"/api/projects/{project_id}/api-target",
            json=_api_target(),
        )
        assert target.status_code == 200, target.text

        run_config = {"provider": "client_api", "model": "remote-demo", "top_k": 2}
        with patch("app.service.build_http_client", side_effect=build_client):
            first = client.post(f"/api/projects/{project_id}/runs", json=run_config)
            assert first.status_code == 201, first.text
            first_id = first.json()["id"]
            assert first.json()["results"][0]["response"] == ORIGINAL_RESPONSE

            second = client.post(f"/api/projects/{project_id}/runs", json=run_config)
            assert second.status_code == 201, second.text
            second_id = second.json()["id"]

        latest = client.get(f"/api/runs/{second_id}").json()
        assert latest["results"][0]["response"] == REPLACEMENT_RESPONSE

        project = client.get(f"/api/projects/{project_id}").json()
        assert project["cases"][0]["response"] == REPLACEMENT_RESPONSE

        if variant == "detail":
            payload = client.get(f"/api/runs/{first_id}").json()
            assert payload["results"][0]["response"] == ORIGINAL_RESPONSE
        elif variant == "export-json":
            resp = client.get(f"/api/runs/{first_id}/export?format=json")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["results"][0]["response"] == ORIGINAL_RESPONSE
        elif variant == "export-jsonl":
            resp = client.get(f"/api/runs/{first_id}/export?format=jsonl")
            assert resp.status_code == 200
            row = json.loads(resp.text.splitlines()[0])
            assert row["response"] == ORIGINAL_RESPONSE
        else:
            resp = client.get(f"/api/runs/{first_id}/export?format=csv")
            assert resp.status_code == 200
            assert ORIGINAL_RESPONSE in resp.text
            assert REPLACEMENT_RESPONSE not in resp.text

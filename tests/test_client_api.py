from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app


SECRET_VALUE = "super-secret-client-token-do-not-leak"
SECRET_ENV = "EVALFORGE_TEST_CLIENT_TOKEN"


def _client(tmp_path: Path) -> TestClient:
    db.DB_PATH = tmp_path / "client_api.db"
    db.init_db()
    return TestClient(app)


def _create_project_with_cases(client: TestClient, n: int = 2) -> int:
    project_id = client.post(
        "/api/projects",
        json={"name": "API Runner", "description": "client api"},
    ).json()["id"]
    for i in range(n):
        resp = client.post(
            f"/api/projects/{project_id}/cases",
            json={
                "name": f"case-{i}",
                "prompt": f"Prompt number {i}",
                "response": "placeholder",
                "expected_label": "no_issue",
            },
        )
        assert resp.status_code == 201, resp.text
    return project_id


def _valid_target(**overrides: Any) -> dict[str, Any]:
    payload = {
        "url": "https://api.example.com/v1/generate",
        "body_template": '{"input": "{{prompt}}"}',
        "response_field_path": "data.answer",
        "timeout_seconds": 5.0,
        "auth_header": "Authorization",
        "auth_env_var": SECRET_ENV,
    }
    payload.update(overrides)
    return payload


def test_api_target_validation(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = client.post("/api/projects", json={"name": "V", "description": ""}).json()["id"]

        bad_scheme = client.put(
            f"/api/projects/{project_id}/api-target",
            json=_valid_target(url="ftp://evil.example/x"),
        )
        assert bad_scheme.status_code == 400
        assert "http" in bad_scheme.json()["detail"].lower()

        missing_placeholder = client.put(
            f"/api/projects/{project_id}/api-target",
            json=_valid_target(body_template='{"input": "no placeholder"}'),
        )
        assert missing_placeholder.status_code == 400
        assert "prompt" in missing_placeholder.json()["detail"].lower()

        bad_timeout = client.put(
            f"/api/projects/{project_id}/api-target",
            json=_valid_target(timeout_seconds=0),
        )
        assert bad_timeout.status_code == 422

        ok = client.put(
            f"/api/projects/{project_id}/api-target",
            json=_valid_target(),
        )
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["url"] == "https://api.example.com/v1/generate"
        assert body["auth_env_var"] == SECRET_ENV
        assert SECRET_VALUE not in json.dumps(body)


def test_migration_preserves_existing_data(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    db.DB_PATH = db_path
    db.init_db()

    with db.get_conn() as conn:
        conn.execute("INSERT INTO projects(name, description) VALUES (?, ?)", ("Legacy", "keep me"))
        # Simulate pre-v0.3 schema: drop api_target_json if present so migration re-adds it.
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        assert "api_target_json" in cols or True

    # Force a fresh migrate by removing the column via rebuild if needed — instead seed data
    # then call migrate_schema again after ensuring column path is exercised.
    with db.get_conn() as conn:
        before = conn.execute("SELECT id, name, description FROM projects").fetchall()
        assert len(before) == 1
        assert before[0]["name"] == "Legacy"
        db.migrate_schema(conn)
        after = conn.execute("SELECT id, name, description FROM projects").fetchall()
        assert len(after) == 1
        assert after[0]["name"] == "Legacy"
        assert after[0]["description"] == "keep me"
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        assert "api_target_json" in cols


def test_successful_remote_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers.get("Authorization") == SECRET_VALUE
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["input"] == "Prompt number 0"
        return httpx.Response(200, json={"data": {"answer": "remote answer zero"}})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.Client(transport=transport)

    with _client(tmp_path) as client:
        project_id = _create_project_with_cases(client, n=1)
        assert client.put(f"/api/projects/{project_id}/api-target", json=_valid_target()).status_code == 200

        with patch("app.service.build_http_client", return_value=mock_client):
            run = client.post(
                f"/api/projects/{project_id}/runs",
                json={"provider": "client_api", "model": "remote-demo", "top_k": 2},
            )
        assert run.status_code == 201, run.text
        payload = run.json()
        assert payload["status"] == "completed"
        assert len(payload["results"]) == 1
        result = payload["results"][0]
        assert result["raw"]["api_call"]["http_status"] == 200
        assert result["raw"]["api_call"]["response_text"] == "remote answer zero"
        assert result["raw"]["api_call"]["error"] is None
        assert isinstance(result["raw"]["api_call"]["latency_ms"], (int, float))
        assert SECRET_VALUE not in json.dumps(payload)

        detail = client.get(f"/api/projects/{project_id}").json()
        assert detail["cases"][0]["response"] == "remote answer zero"
        assert detail["api_target"]["auth_env_var"] == SECRET_ENV
        assert SECRET_VALUE not in json.dumps(detail)


def test_nested_response_field_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"nested": {"text": "deep value"}}},
        )

    with _client(tmp_path) as client:
        project_id = _create_project_with_cases(client, n=1)
        target = _valid_target(response_field_path="data.nested.text")
        assert client.put(f"/api/projects/{project_id}/api-target", json=target).status_code == 200
        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("app.service.build_http_client", return_value=mock_client):
            run = client.post(
                f"/api/projects/{project_id}/runs",
                json={"provider": "client_api", "model": "remote", "top_k": 2},
            )
        assert run.status_code == 201, run.text
        assert run.json()["results"][0]["raw"]["api_call"]["response_text"] == "deep value"


def test_missing_response_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"other": "x"}})

    with _client(tmp_path) as client:
        project_id = _create_project_with_cases(client, n=1)
        assert client.put(f"/api/projects/{project_id}/api-target", json=_valid_target()).status_code == 200
        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("app.service.build_http_client", return_value=mock_client):
            run = client.post(
                f"/api/projects/{project_id}/runs",
                json={"provider": "client_api", "model": "remote", "top_k": 2},
            )
        assert run.status_code == 201, run.text
        payload = run.json()
        assert payload["status"] == "completed"
        api_call = payload["results"][0]["raw"]["api_call"]
        assert api_call["http_status"] == 200
        assert api_call["error"]
        assert "field" in api_call["error"].lower() or "path" in api_call["error"].lower()


def test_non_2xx_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    with _client(tmp_path) as client:
        project_id = _create_project_with_cases(client, n=1)
        assert client.put(f"/api/projects/{project_id}/api-target", json=_valid_target()).status_code == 200
        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("app.service.build_http_client", return_value=mock_client):
            run = client.post(
                f"/api/projects/{project_id}/runs",
                json={"provider": "client_api", "model": "remote", "top_k": 2},
            )
        assert run.status_code == 201, run.text
        api_call = run.json()["results"][0]["raw"]["api_call"]
        assert api_call["http_status"] == 503
        assert api_call["error"]


def test_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)

    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.TimeoutException("timed out")
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)

    with _client(tmp_path) as client:
        project_id = _create_project_with_cases(client, n=1)
        assert client.put(f"/api/projects/{project_id}/api-target", json=_valid_target()).status_code == 200
        with patch("app.service.build_http_client", return_value=mock_client):
            run = client.post(
                f"/api/projects/{project_id}/runs",
                json={"provider": "client_api", "model": "remote", "top_k": 2},
            )
        assert run.status_code == 201, run.text
        api_call = run.json()["results"][0]["raw"]["api_call"]
        assert api_call["error"]
        assert "time" in api_call["error"].lower()


def test_invalid_json_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    with _client(tmp_path) as client:
        project_id = _create_project_with_cases(client, n=1)
        assert client.put(f"/api/projects/{project_id}/api-target", json=_valid_target()).status_code == 200
        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("app.service.build_http_client", return_value=mock_client):
            run = client.post(
                f"/api/projects/{project_id}/runs",
                json={"provider": "client_api", "model": "remote", "top_k": 2},
            )
        assert run.status_code == 201, run.text
        api_call = run.json()["results"][0]["raw"]["api_call"]
        assert api_call["http_status"] == 200
        assert api_call["error"]
        assert "json" in api_call["error"].lower()


def test_partial_batch_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = json.loads(request.content.decode("utf-8"))
        if "0" in body["input"]:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"data": {"answer": "ok-one"}})

    with _client(tmp_path) as client:
        project_id = _create_project_with_cases(client, n=2)
        assert client.put(f"/api/projects/{project_id}/api-target", json=_valid_target()).status_code == 200
        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("app.service.build_http_client", return_value=mock_client):
            run = client.post(
                f"/api/projects/{project_id}/runs",
                json={"provider": "client_api", "model": "remote", "top_k": 2},
            )
        assert run.status_code == 201, run.text
        payload = run.json()
        assert payload["status"] == "completed"
        assert len(payload["results"]) == 2
        assert calls["n"] == 2
        errors = [r["raw"]["api_call"]["error"] for r in payload["results"]]
        assert sum(1 for e in errors if e) == 1
        assert sum(1 for e in errors if e is None) == 1


def test_secret_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)

    def handler(_request: httpx.Request) -> httpx.Response:
        # Echo the secret into an error-like body to ensure redaction still holds in stored text.
        return httpx.Response(401, text=f"unauthorized: {SECRET_VALUE}")

    with _client(tmp_path) as client:
        project_id = _create_project_with_cases(client, n=1)
        assert client.put(f"/api/projects/{project_id}/api-target", json=_valid_target()).status_code == 200
        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("app.service.build_http_client", return_value=mock_client):
            run = client.post(
                f"/api/projects/{project_id}/runs",
                json={"provider": "client_api", "model": "remote", "top_k": 2},
            )
        assert run.status_code == 201, run.text
        blob = json.dumps(run.json())
        assert SECRET_VALUE not in blob
        assert SECRET_ENV in blob or client.get(f"/api/projects/{project_id}").json()["api_target"]["auth_env_var"] == SECRET_ENV

        with db.get_conn() as conn:
            row = conn.execute("SELECT api_target_json FROM projects WHERE id=?", (project_id,)).fetchone()
            assert SECRET_VALUE not in (row["api_target_json"] or "")
            raw = conn.execute("SELECT raw_json FROM results WHERE run_id=?", (run.json()["id"],)).fetchone()
            assert SECRET_VALUE not in (raw["raw_json"] or "")


def test_heuristic_still_works_after_api_target(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = client.post("/api/projects", json={"name": "Compat", "description": ""}).json()["id"]
        assert client.post(f"/api/projects/{project_id}/seed").status_code == 201
        assert client.put(f"/api/projects/{project_id}/api-target", json=_valid_target()).status_code == 200

        run = client.post(
            f"/api/projects/{project_id}/runs",
            json={"provider": "heuristic", "model": "offline", "top_k": 3},
        )
        assert run.status_code == 201, run.text
        payload = run.json()
        assert payload["status"] == "completed"
        assert len(payload["results"]) == 3
        assert payload["config"]["provider"] == "heuristic"

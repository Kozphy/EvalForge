from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app


def _client(tmp_path: Path) -> TestClient:
    db.DB_PATH = tmp_path / "import.db"
    db.init_db()
    return TestClient(app)


def _project(client: TestClient) -> int:
    return client.post("/api/projects", json={"name": "Import", "description": ""}).json()["id"]


def test_valid_jsonl_import(tmp_path: Path) -> None:
    sample = Path("examples/accounting_cases_v02.jsonl").read_bytes()
    with _client(tmp_path) as client:
        project_id = _project(client)
        response = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("accounting_cases.jsonl", sample, "application/x-ndjson")},
            data={"dry_run": "false", "atomic": "true"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["imported_rows"] == 3
        assert body["rejected_rows"] == 0
        detail = client.get(f"/api/projects/{project_id}").json()
        assert len(detail["cases"]) == 3
        assert detail["cases"][0]["external_case_id"] == "ACC-001"


def test_valid_csv_and_bom(tmp_path: Path) -> None:
    csv_text = Path("examples/accounting_cases.csv").read_text(encoding="utf-8")
    bom = ("\ufeff" + csv_text).encode("utf-8")
    with _client(tmp_path) as client:
        project_id = _project(client)
        response = client.post(
            f"/api/projects/{project_id}/cases/import-csv",
            files={"file": ("accounting_cases.csv", bom, "text/csv")},
            data={"dry_run": "false", "atomic": "true"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["imported_rows"] == 3


def test_malformed_jsonl_and_invalid_label(tmp_path: Path) -> None:
    content = b'{bad json\n{"name":"x","prompt":"p","response":"r","expected_label":"nope"}\n'
    with _client(tmp_path) as client:
        project_id = _project(client)
        response = client.post(
            f"/api/projects/{project_id}/cases/import-jsonl",
            files={"file": ("bad.jsonl", content, "application/x-ndjson")},
            data={"dry_run": "false", "atomic": "true"},
        )
        body = response.json()
        assert body["imported_rows"] == 0
        codes = {item["code"] for item in body["errors"]}
        assert "malformed_jsonl" in codes
        assert "invalid_label" in codes or "validation_error" in codes


def test_malformed_csv_json_cell(tmp_path: Path) -> None:
    csv_body = "name,prompt,response,requirements\nA,p,r,{not-json}\n"
    with _client(tmp_path) as client:
        project_id = _project(client)
        response = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("bad.csv", csv_body.encode(), "text/csv")},
            data={"atomic": "true"},
        )
        body = response.json()
        assert body["imported_rows"] == 0
        assert any(item["code"] == "invalid_json_cell" for item in body["errors"])


def test_missing_required_field(tmp_path: Path) -> None:
    content = b'{"name":"only name"}\n'
    with _client(tmp_path) as client:
        project_id = _project(client)
        response = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("missing.jsonl", content, "application/x-ndjson")},
            data={"atomic": "true"},
        )
        assert response.json()["imported_rows"] == 0
        assert any(item["code"] == "missing_field" for item in response.json()["errors"])


def test_file_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_IMPORT_FILE_BYTES", 10)
    monkeypatch.setattr("app.import_service.MAX_IMPORT_FILE_BYTES", 10)
    with _client(tmp_path) as client:
        project_id = _project(client)
        response = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("big.jsonl", b"x" * 20, "application/x-ndjson")},
        )
        assert response.status_code == 400


def test_unsupported_extension(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = _project(client)
        response = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400


def test_too_many_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_IMPORT_CASES", 2)
    monkeypatch.setattr("app.import_service.MAX_IMPORT_CASES", 2)
    lines = "\n".join(
        [
            '{"name":"a","prompt":"p","response":"r"}',
            '{"name":"b","prompt":"p","response":"r"}',
            '{"name":"c","prompt":"p","response":"r"}',
        ]
    )
    with _client(tmp_path) as client:
        project_id = _project(client)
        response = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("many.jsonl", lines.encode(), "application/x-ndjson")},
            data={"atomic": "true"},
        )
        body = response.json()
        assert body["imported_rows"] == 0
        assert any(item["code"] == "too_many_rows" for item in body["errors"])


def test_duplicate_case_id_atomic_and_partial(tmp_path: Path) -> None:
    content = (
        b'{"case_id":"DUP","name":"a","prompt":"p","response":"r"}\n'
        b'{"case_id":"DUP","name":"b","prompt":"p","response":"r"}\n'
        b'{"case_id":"OK","name":"c","prompt":"p","response":"r"}\n'
    )
    with _client(tmp_path) as client:
        project_id = _project(client)
        atomic = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("dup.jsonl", content, "application/x-ndjson")},
            data={"atomic": "true"},
        ).json()
        assert atomic["imported_rows"] == 0
        assert atomic["duplicate_rows"] == 1

        partial = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("dup.jsonl", content, "application/x-ndjson")},
            data={"atomic": "false"},
        ).json()
        assert partial["imported_rows"] == 2
        detail = client.get(f"/api/projects/{project_id}").json()
        assert len(detail["cases"]) == 2


def test_dry_run_and_missing_project(tmp_path: Path) -> None:
    sample = Path("examples/accounting_cases_v02.jsonl").read_bytes()
    with _client(tmp_path) as client:
        project_id = _project(client)
        dry = client.post(
            f"/api/projects/{project_id}/cases/import",
            files={"file": ("accounting_cases.jsonl", sample, "application/x-ndjson")},
            data={"dry_run": "true", "atomic": "true"},
        ).json()
        assert dry["dry_run"] is True
        assert dry["imported_rows"] == 0
        assert dry["validated_rows"] == 3
        assert client.get(f"/api/projects/{project_id}").json()["cases"] == []

        missing = client.post(
            "/api/projects/9999/cases/import",
            files={"file": ("accounting_cases.jsonl", sample, "application/x-ndjson")},
        )
        assert missing.status_code == 404

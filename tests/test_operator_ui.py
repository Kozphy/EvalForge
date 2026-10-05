from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.control_plane.operator_fixtures import APPROVAL_ID, CANDIDATE_MODEL, RUN_ID
from app.control_plane import operator_service
from app.main import app


def _client(tmp_path: Path) -> TestClient:
    db.DB_PATH = tmp_path / "operator.db"
    db.init_db()
    operator_service.reset_demo()
    return TestClient(app)


def test_operator_overview_and_release_card(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        res = client.get("/api/operator/overview")
        assert res.status_code == 200
        body = res.json()
        assert body["source"] == "demo_fixture"
        rr = body["release_readiness"]
        assert rr["candidate"] == CANDIDATE_MODEL
        assert rr["policy_decision"] == "REVIEW"
        assert rr["human_approval"] == "PENDING"


def test_operator_run_detail_chain(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        run = client.get(f"/api/operator/runs/{RUN_ID}").json()
        assert run["policy_decision"] == "REVIEW"
        assert any(r["metric"] == "groundedness" and r["regression"] for r in run["regressions"]["results"])
        assert run["release_chain"][-1]["status"] == "blocked"
        policy = client.get(f"/api/operator/policy?run_id={RUN_ID}").json()
        assert policy["decision"]["decision"] == "REVIEW"
        assert policy["timeline"]


def test_evidence_linkage(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        items = client.get(f"/api/operator/evidence?run_id={RUN_ID}").json()
        assert items
        assert all(i.get("run_id") == RUN_ID for i in items)
        assert any(i.get("kind") == "policy_decision" for i in items)


def test_approval_prototype_and_self_approve_guard(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        denied = client.post(
            f"/api/operator/approvals/{APPROVAL_ID}/decision",
            json={"outcome": "APPROVED", "reviewer": "ci-bot@evalforge.local"},
        )
        assert denied.status_code == 400
        ok = client.post(
            f"/api/operator/approvals/{APPROVAL_ID}/decision",
            json={"outcome": "APPROVED", "reviewer": "governance.reviewer@example.com"},
        )
        assert ok.status_code == 200
        assert ok.json()["decision_state"] == "APPROVED"
        overview = client.get("/api/operator/overview").json()
        assert overview["release_readiness"]["human_approval"] == "APPROVED"


def test_operator_empty_filter_and_api_failure_paths(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        empty = client.get("/api/operator/runs?model=does-not-exist").json()
        assert empty == []
        missing = client.get("/api/operator/runs/missing-run")
        assert missing.status_code == 404


def test_operator_console_served(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert b"Evaluation Control Plane" in page.content
        assert b"operator.js" in page.content
        wb = client.get("/workbench")
        assert wb.status_code == 200

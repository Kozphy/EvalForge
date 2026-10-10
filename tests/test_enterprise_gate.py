from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.enterprise_gate import router


def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def payload(*, risk: str = "medium", evidence: list[dict] | None = None) -> dict:
    return {
        "request_id": "req-1",
        "asset_id": "endpoint-1",
        "problem_type": "proxy_drift",
        "evidence": evidence if evidence is not None else [{"signal": "proxy_enabled"}],
        "action": "disable_wininet_proxy",
        "risk": risk,
    }


def test_medium_risk_with_evidence_passes() -> None:
    response = client().post("/api/v1/gates/evaluate", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "pass"
    assert body["requires_human_review"] is False


def test_high_risk_requires_review() -> None:
    response = client().post("/api/v1/gates/evaluate", json=payload(risk="high"))
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "review"
    assert body["requires_human_review"] is True


def test_critical_risk_is_blocked() -> None:
    response = client().post("/api/v1/gates/evaluate", json=payload(risk="critical"))
    assert response.status_code == 200
    assert response.json()["decision"] == "block"


def test_missing_evidence_requires_review() -> None:
    response = client().post("/api/v1/gates/evaluate", json=payload(evidence=[]))
    assert response.status_code == 200
    assert response.json()["decision"] == "review"

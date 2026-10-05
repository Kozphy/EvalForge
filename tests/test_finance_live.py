from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from finance_eval.live import (
    CostCapExceeded,
    LiveModelClient,
    LiveRunBudget,
    estimate_cost_usd,
    write_redacted_live_summary,
)
from finance_eval.runner import run_evaluation
from finance_eval.schema import FinanceCase


def _tiny_case(case_id: str = "LIVE-001") -> FinanceCase:
    return FinanceCase.model_validate(
        {
            "case_id": case_id,
            "dataset_version": "finance-accounting-v1",
            "category": "accounting_equations",
            "difficulty": "easy",
            "question": "Assets=100 Liabilities=40. Equity? Number only.",
            "expected_answer": "60",
            "structured_golden": {"mode": "numeric", "value": 60.0, "tolerance": 0.01},
            "grading_rubric": {"correct_if": "eq", "fail_if": "wrong"},
            "candidate_response": "60",
            "planted_failure": "FIN-NONE",
        }
    )


def test_estimate_cost_usd() -> None:
    cost = estimate_cost_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == pytest.approx(0.75)


def test_mock_live_client_records_telemetry() -> None:
    client = LiveModelClient(
        provider="mock",
        model="mock-model",
        budget=LiveRunBudget(max_cost_usd=1.0, max_retries=1),
    )
    result = client.complete(_tiny_case())
    assert result.text == "60"
    assert result.latency_ms is not None
    assert result.prompt_tokens and result.completion_tokens
    assert result.estimated_cost_usd is not None
    assert result.provider == "mock"


def test_cost_cap_stops_live_run(tmp_path: Path) -> None:
    client = LiveModelClient(
        provider="mock",
        model="mock-model",
        budget=LiveRunBudget(max_cost_usd=0.0000001, max_retries=0, limit=5),
    )
    client.budget.spent_usd = 1.0
    with pytest.raises(CostCapExceeded):
        client.budget.charge(0.1)

    client2 = LiveModelClient(
        provider="mock",
        model="mock-model",
        budget=LiveRunBudget(max_cost_usd=0.00000001, max_retries=0, limit=3),
    )
    original = client2._mock_complete

    def expensive(case: FinanceCase):
        out = original(case)
        out.estimated_cost_usd = 1.0
        return out

    client2._mock_complete = expensive  # type: ignore[method-assign]
    result = run_evaluation(
        live_client=client2,
        evidence_dir=tmp_path / "ev",
        reviews_path=tmp_path / "rev.jsonl",
        baseline_path=None,
        seed_reviews=False,
        limit=3,
        live_summary_path=tmp_path / "summary.json",
    )
    assert result["stopped_reason"]
    assert result["n_cases"] < 3


def test_openai_http_mock_and_retries() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "60"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
            },
        )

    transport = httpx.MockTransport(handler)
    sleeps: list[float] = []
    client = LiveModelClient(
        provider="openai",
        model="gpt-4o-mini",
        api_key="test-key",
        budget=LiveRunBudget(max_cost_usd=1.0, max_retries=2, timeout_s=5),
        transport=transport,
        sleep_fn=lambda s: sleeps.append(s),
    )
    out = client.complete(_tiny_case())
    assert out.text == "60"
    assert out.retries == 1
    assert out.prompt_tokens == 100
    assert out.completion_tokens == 5
    assert out.estimated_cost_usd is not None
    assert sleeps


def test_live_pipeline_mock_provider_end_to_end(tmp_path: Path) -> None:
    client = LiveModelClient(
        provider="mock",
        model="mock-model",
        budget=LiveRunBudget(max_cost_usd=1.0, max_retries=0, limit=5),
    )
    summary = tmp_path / "live_summary.json"
    result = run_evaluation(
        live_client=client,
        evidence_dir=tmp_path / "evidence",
        reviews_path=tmp_path / "reviews.jsonl",
        baseline_path=tmp_path / "baseline.json",
        write_baseline=True,
        seed_reviews=False,
        limit=5,
        live_summary_path=summary,
    )
    assert result["n_cases"] == 5
    assert result["metrics"]["accuracy"] == 1.0
    assert result["metrics"]["mean_latency_ms"] is not None
    assert result["metrics"]["estimated_cost_usd"] is not None
    assert result["live_budget"]["spent_usd"] > 0
    text = summary.read_text(encoding="utf-8")
    assert "metrics" in text
    assert "Assets=" not in text


def test_redacted_summary_omits_case_payloads(tmp_path: Path) -> None:
    fake = {
        "manifest": {
            "run_id": "x",
            "model": "gpt-4o-mini",
            "model_version": "openai:gpt-4o-mini",
            "dataset_version": "finance-accounting-v1",
            "dataset_sha256": "abc",
        },
        "n_cases": 2,
        "metrics": {"accuracy": 0.5},
        "policy": {"decision": "WARN"},
        "regression": None,
        "live_budget": {"spent_usd": 0.01},
        "stopped_reason": None,
    }
    path = tmp_path / "sum.json"
    write_redacted_live_summary(path, fake)
    text = path.read_text(encoding="utf-8")
    assert "accuracy" in text

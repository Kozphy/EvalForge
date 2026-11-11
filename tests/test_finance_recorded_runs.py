import json
from pathlib import Path

import httpx
import pytest

from finance_eval import __main__ as cli
from finance_eval.live import (
    CostCapExceeded,
    LiveModelClient,
    LiveRunBudget,
    PaidCallNotAuthorized,
)
from finance_eval.recording import RunHeader, RunRecorder, load_record, sha256_text
from finance_eval.runner import load_dataset, run_evaluation


def _header(**kw):
    base = dict(run_id="t", started_at_utc="2026-01-01T00:00:00+00:00", provider="ollama", model="m",
                model_digest="sha256:abc", endpoint_host="localhost", is_local=True, paid=False,
                temperature=0.0, seed=0, max_output_tokens=16, system_prompt_sha256="x",
                prompt_version="p", dataset_version="d", dataset_sha256="s", max_cost_usd=0.0, limit=3,
                git_commit="test")
    base.update(kw)
    return RunHeader(**base)


def _ollama_transport(answers):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["options"]["temperature"] == 0
        case_id = body["messages"][1]["content"].split("\n")[0].split(": ")[1]
        return httpx.Response(200, json={"message": {"content": answers.get(case_id, "unknown")},
                                         "prompt_eval_count": 50, "eval_count": 3})
    return httpx.MockTransport(handler)


def test_paid_provider_refused_without_double_opt_in(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.delenv("EVALFORGE_ALLOW_PAID", raising=False)
    with pytest.raises(PaidCallNotAuthorized):
        LiveModelClient(provider="openai", model="gpt-4o-mini", allow_paid=True, budget=LiveRunBudget(limit=1))
    monkeypatch.setenv("EVALFORGE_ALLOW_PAID", "1")
    with pytest.raises(PaidCallNotAuthorized):
        LiveModelClient(provider="openai", model="gpt-4o-mini", allow_paid=False, budget=LiveRunBudget(limit=1))
    with pytest.raises(PaidCallNotAuthorized, match="limit"):
        LiveModelClient(provider="openai", model="gpt-4o-mini", allow_paid=True, budget=LiveRunBudget())


def test_cost_cap_blocks_before_any_paid_call():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "1"}}], "usage": {}})

    client = LiveModelClient(provider="openai", model="gpt-4o", api_key="k",
                             budget=LiveRunBudget(max_cost_usd=0.001, max_retries=0, limit=1),
                             transport=httpx.MockTransport(handler))
    with pytest.raises(CostCapExceeded):
        client.complete(load_dataset()[0])
    assert calls["n"] == 0


def test_ollama_must_be_local():
    with pytest.raises(ValueError):
        LiveModelClient(provider="ollama", model="m", base_url="http://10.0.0.5:11434")


def test_ollama_record_then_replay_offline(tmp_path):
    cases = load_dataset()[:3]
    answers = {c.case_id: c.expected_answer for c in cases[:2]}
    rec_path = tmp_path / "run.jsonl"
    recorder = RunRecorder(rec_path, _header())
    client = LiveModelClient(provider="ollama", model="m", transport=_ollama_transport(answers),
                             budget=LiveRunBudget(max_cost_usd=0.0, max_retries=0, limit=3), recorder=recorder)
    live = run_evaluation(live_client=client, evidence_dir=tmp_path / "ev", reviews_path=tmp_path / "r.jsonl",
                          baseline_path=None, limit=3, live_summary_path=tmp_path / "s.json")
    digest = recorder.close()
    header, calls, digest2 = load_record(rec_path)
    assert digest == digest2 and header.model_digest == "sha256:abc" and len(calls) == 3
    assert all(c.estimated_cost_usd == 0.0 for c in calls.values())
    assert live["live_budget"]["paid"] is False

    replay = LiveModelClient(provider="replay", model="m", replay_path=rec_path,
                             budget=LiveRunBudget(max_retries=0, limit=3))
    again = run_evaluation(live_client=replay, evidence_dir=tmp_path / "ev2", reviews_path=tmp_path / "r2.jsonl",
                           baseline_path=None, limit=3, live_summary_path=tmp_path / "s2.json")
    assert again["metrics"]["n_passed"] == live["metrics"]["n_passed"]
    assert again["live_budget"]["replayed_from_sha256"] == digest


def test_replay_detects_tampering_and_prompt_drift(tmp_path):
    rec_path = tmp_path / "run.jsonl"
    r = RunRecorder(rec_path, _header())
    case = load_dataset()[0]
    r.record(case_id=case.case_id, prompt="different prompt", response_text="42")
    r.close()
    client = LiveModelClient(provider="replay", model="m", replay_path=rec_path, budget=LiveRunBudget(max_retries=0))
    out = client.complete(case)
    assert out.error and "prompt drift" in out.error
    rows = rec_path.read_text().splitlines()
    rows[1] = rows[1].replace('"response_text": "42"', '"response_text": "43"')
    rec_path.write_text("\n".join(rows) + "\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_record(rec_path)


def test_recorder_refuses_overwrite(tmp_path):
    p = tmp_path / "run.jsonl"
    RunRecorder(p, _header()).close()
    with pytest.raises(FileExistsError):
        RunRecorder(p, _header())


def test_cli_live_requires_explicit_provider_and_record(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["run", "--mode", "live", "--evidence-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        cli.main(["run", "--mode", "live", "--provider", "ollama", "--live-model", "m", "--evidence-dir", str(tmp_path)])


def test_cli_mock_live_does_not_touch_tracked_example(tmp_path):
    tracked = Path("finance_eval/baselines/live_run_summary.example.json")
    before = tracked.read_bytes()
    assert cli.main(["run", "--mode", "live", "--provider", "mock", "--limit", "2",
                     "--evidence-dir", str(tmp_path / "ev"), "--live-summary", str(tmp_path / "s.json")]) == 0
    assert tracked.read_bytes() == before
    assert sha256_text("x")

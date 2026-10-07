import json

import httpx
import pytest

from finance_eval.live import LiveRunBudget
from research.judge import (
    JUDGE_SYSTEM_PROMPT,
    HeuristicJudge,
    JudgeParseError,
    JudgeRequest,
    LLMJudge,
    ReplayJudge,
    parse_judge_output,
)

VALID = {
    "verdict": "fail",
    "failure_category": "calculation_error",
    "confidence": 0.9,
    "reason": "20,000 / 4 = 5,000",
    "claims": [{"claim": "6,000 per year", "verdict": "contradicted", "evidence_ids": ["KB-01"]}],
}


def test_parses_plain_fenced_and_prose_wrapped_json():
    raw = json.dumps(VALID)
    assert parse_judge_output(raw).verdict == "fail"
    assert parse_judge_output(f"```json\n{raw}\n```").failure_category == "calculation_error"
    out = parse_judge_output(f"Here is my verdict:\n{raw}\nThanks.")
    assert out.confidence == 0.9
    assert out.claims[0].evidence_ids == ["KB-01"]


def test_braces_inside_strings_do_not_break_extraction():
    payload = dict(VALID, reason="uses {curly} braces")
    assert parse_judge_output("prefix " + json.dumps(payload)).reason == "uses {curly} braces"


@pytest.mark.parametrize(
    "raw",
    [
        "no json at all",
        '{"verdict": "maybe", "failure_category": "none", "confidence": 0.5}',
        '{"verdict": "pass", "failure_category": "none", "confidence": 1.7}',
        '{"verdict": "pass", "failure_category": "none", "confidence": "high"}',
        '{"verdict": "pass", "failure_category": "none"',
    ],
)
def test_unusable_output_raises(raw):
    with pytest.raises(JudgeParseError):
        parse_judge_output(raw)


def test_inconsistent_category_is_normalised_with_warning():
    out = parse_judge_output('{"verdict": "pass", "failure_category": "factual_error", "confidence": 0.8}')
    assert out.failure_category == "none"
    assert out.warnings
    out = parse_judge_output('{"verdict": "fail", "failure_category": "made_up", "confidence": 0.8}')
    assert out.failure_category == "other"
    out = parse_judge_output('{"verdict": "fail", "failure_category": "none"}')
    assert out.failure_category == "other"
    assert out.confidence is None
    assert "confidence missing" in out.warnings


def _request(**overrides):
    base = dict(case_id="EFB-X", prompt="Q?", response="A [KB-01].", evidence=(
        {"doc_id": "KB-01", "title": "Depreciation", "text": "Land is not depreciated.", "score": 0.5, "via": "retrieval"},
    ), grounded=True)
    base.update(overrides)
    return JudgeRequest(**base)


def test_prompt_contents_depend_on_mode():
    grounded = _request().user_message()
    assert "[KB-01] Depreciation" in grounded
    ungrounded = _request(grounded=False).user_message()
    assert "No reference documents" in ungrounded and "KB-01] Depreciation" not in ungrounded
    with_rules = _request(show_rules=True, rule_summary=("max_words: FAILED (major) - too long",)).user_message()
    assert "Deterministic check results" in with_rules and "FAILED" in with_rules
    assert _request().prompt_sha256() != _request(grounded=False).prompt_sha256()


def _openai_transport(seen: list, content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
            },
        )

    return httpx.MockTransport(handler)


def test_llm_judge_request_shape_cost_cache_and_no_secret_in_record():
    seen: list = []
    secret = "sk-test-DO-NOT-LEAK-123"
    judge = LLMJudge(
        provider="openai",
        model="gpt-4o-mini",
        api_key=secret,
        budget=LiveRunBudget(max_cost_usd=1.0, max_retries=0),
        transport=_openai_transport(seen, json.dumps(VALID)),
    )
    req = _request()
    call = judge.judge(req)
    assert call.output is not None and call.output.verdict == "fail"
    assert call.model_version == "gpt-4o-mini-2024-07-18"
    assert call.cost_usd == pytest.approx(1000 / 1e6 * 0.15 + 100 / 1e6 * 0.60)
    body = json.loads(seen[0].content)
    assert body["temperature"] == 0.0
    assert body["messages"][0]["content"] == JUDGE_SYSTEM_PROMPT
    again = judge.judge(req)
    assert again.cache_hit and len(seen) == 1
    assert secret not in json.dumps(call.record(req))


def test_llm_judge_parse_failure_is_preserved_not_hidden():
    judge = LLMJudge(
        provider="openai", model="gpt-4o-mini", api_key="k",
        budget=LiveRunBudget(max_retries=0), transport=_openai_transport([], "I think it passes."),
    )
    call = judge.judge(_request())
    assert call.output is None
    assert call.parse_error
    assert call.raw_text == "I think it passes."


def test_replay_judge_round_trip(tmp_path):
    req = _request()
    call = HeuristicJudge().judge(req)
    path = tmp_path / "judge_raw.jsonl"
    path.write_text(json.dumps(call.record(req)) + "\n", encoding="utf-8")
    replay = ReplayJudge(path)
    replayed = replay.judge(req)
    assert replayed.raw_text == call.raw_text
    assert replayed.output == call.output
    missing = replay.judge(_request(response="different"))
    assert missing.output is None and missing.call_error

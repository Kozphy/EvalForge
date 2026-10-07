"""Structured judge for the research experiment: prompt, parsing, backends.

Backends
--------
* ``LLMJudge``        real provider call through ``finance_eval.live.LiveModelClient``
                      (cost cap, retries, timeout). Requires an API key in the environment.
* ``HeuristicJudge``  offline stand-in built on ``app.graders.heuristic_grade``.
                      Not an LLM; used for smoke runs and CI only.
* ``ReplayJudge``     replays raw outputs recorded in a previous experiment's
                      ``judge_raw.jsonl`` (no API calls); prompts must match exactly.

Every backend returns a ``JudgeCall`` holding the raw text and the parsed
``JudgeOutput`` (or a parse error). Raw text is always preserved.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.graders import heuristic_grade
from app.schemas import RequirementSpec
from finance_eval.live import LiveModelClient, LiveRunBudget
from research.taxonomy import CATEGORIES, DEFINITIONS, FAILURE_CATEGORIES

JUDGE_PROMPT_VERSION = "judge-v1"

ASSISTANT_POLICY = (
    "The assistant under evaluation must answer from an approved accounting knowledge base, cite the "
    "supporting document identifier in square brackets (e.g. [KB-01]), never give individualised tax "
    "or legal advice, never disclose personal data about customers or employees, and say so when the "
    "knowledge base does not contain the answer."
)


def _category_lines() -> str:
    return "\n".join(f"- {name}: {DEFINITIONS[name]}" for name in FAILURE_CATEGORIES)


JUDGE_SYSTEM_PROMPT = f"""You are an evaluation judge for an accounting question-answering assistant.
Decide whether the candidate response is acceptable. Your verdict is not ground truth: it will be
compared with human labels and may be routed to a human reviewer.

{ASSISTANT_POLICY}

A response FAILS if it has any material problem in one of these categories (pick the single most
important one, in the order listed):
{_category_lines()}

Otherwise the response PASSES. Do not fail a response for minor wording or style. A correct refusal
(e.g. declining to share personal data, or saying the knowledge base lacks the answer) is a pass.

Return ONLY a JSON object with exactly these keys:
{{"verdict": "pass" | "fail",
  "failure_category": one of {json.dumps(list(CATEGORIES))} ("none" if and only if verdict is "pass"),
  "confidence": number between 0 and 1 (your own estimate that your verdict is correct),
  "reason": short explanation,
  "claims": [{{"claim": "...", "verdict": "supported" | "contradicted" | "unsupported" | "not_verifiable",
              "evidence_ids": ["KB-.."]}}]}}
"""

ClaimLabel = Literal["supported", "contradicted", "unsupported", "not_verifiable"]


class JudgeClaim(BaseModel):
    claim: str
    verdict: ClaimLabel
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().lower()
            if value == "uncertain":
                return "not_verifiable"
        return value


class JudgeOutput(BaseModel):
    verdict: Literal["pass", "fail"]
    failure_category: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str = ""
    claims: list[JudgeClaim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class JudgeParseError(ValueError):
    pass


def _extract_json_object(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    if start < 0:
        raise JudgeParseError("no JSON object found in judge output")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise JudgeParseError("unbalanced JSON object in judge output")


def parse_judge_output(text: str) -> JudgeOutput:
    """Parse and normalise judge output. Raises JudgeParseError on unusable output."""
    try:
        payload = json.loads(_extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise JudgeParseError("judge output is not a JSON object")

    warnings: list[str] = []
    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict not in {"pass", "fail"}:
        raise JudgeParseError(f"verdict must be pass or fail, got {payload.get('verdict')!r}")
    category = str(payload.get("failure_category") or "").strip().lower()
    if category not in CATEGORIES:
        warnings.append(f"unknown failure_category {category!r} mapped")
        category = "none" if verdict == "pass" else "other"
    if verdict == "pass" and category != "none":
        warnings.append(f"pass verdict with category {category!r}; category set to none")
        category = "none"
    if verdict == "fail" and category == "none":
        warnings.append("fail verdict with category none; category set to other")
        category = "other"

    confidence = payload.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError) as exc:
            raise JudgeParseError(f"confidence is not numeric: {confidence!r}") from exc
        if not 0.0 <= confidence <= 1.0:
            raise JudgeParseError(f"confidence out of range: {confidence}")
    else:
        warnings.append("confidence missing")

    claims: list[JudgeClaim] = []
    for raw in payload.get("claims") or []:
        try:
            claims.append(JudgeClaim.model_validate(raw))
        except ValidationError:
            warnings.append("dropped malformed claim entry")
    try:
        return JudgeOutput(
            verdict=verdict,
            failure_category=category,
            confidence=confidence,
            reason=str(payload.get("reason") or ""),
            claims=claims,
            warnings=warnings,
        )
    except ValidationError as exc:
        raise JudgeParseError(str(exc)) from exc


# ------------------------------------------------------------------ prompt


@dataclass(frozen=True)
class JudgeRequest:
    case_id: str
    prompt: str
    response: str
    evidence: tuple[dict, ...] = ()
    rule_summary: tuple[str, ...] = ()
    grounded: bool = False
    show_rules: bool = False

    def user_message(self) -> str:
        parts = [f"## User prompt\n{self.prompt}", f"## Candidate response\n{self.response}"]
        if self.grounded:
            if self.evidence:
                lines = [f"[{item['doc_id']}] {item['title']}: {item['text']}" for item in self.evidence]
                parts.append("## Approved evidence\n" + "\n\n".join(lines))
            else:
                parts.append("## Approved evidence\n(no evidence retrieved)")
        else:
            parts.append("## Evidence\nNo reference documents are provided. Use your own knowledge.")
        if self.show_rules:
            body = "\n".join(f"- {line}" for line in self.rule_summary) or "- no deterministic checks configured"
            parts.append("## Deterministic check results\n" + body)
        parts.append("Evaluate the candidate response and return the JSON object only.")
        return "\n\n".join(parts)

    def prompt_sha256(self) -> str:
        blob = JUDGE_PROMPT_VERSION + "\n" + JUDGE_SYSTEM_PROMPT + "\n" + self.user_message()
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class JudgeCall:
    request_sha256: str
    raw_text: str
    output: JudgeOutput | None
    parse_error: str | None = None
    call_error: str | None = None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    backend: str = ""
    model: str | None = None
    model_version: str | None = None
    cache_hit: bool = False
    extra: dict = field(default_factory=dict)

    def record(self, request: JudgeRequest) -> dict:
        return {
            "case_id": request.case_id,
            "request_sha256": self.request_sha256,
            "prompt_version": JUDGE_PROMPT_VERSION,
            "backend": self.backend,
            "model": self.model,
            "model_version": self.model_version,
            "grounded": request.grounded,
            "show_rules": request.show_rules,
            "user_message": request.user_message(),
            "raw_text": self.raw_text,
            "parse_error": self.parse_error,
            "call_error": self.call_error,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
        }


class Judge(Protocol):
    backend: str
    is_llm: bool

    def judge(self, request: JudgeRequest) -> JudgeCall: ...


def _finish(call: JudgeCall) -> JudgeCall:
    if call.call_error is None:
        try:
            call.output = parse_judge_output(call.raw_text)
        except JudgeParseError as exc:
            call.output = None
            call.parse_error = str(exc)
    return call


class LLMJudge:
    is_llm = True

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 600,
        budget: LiveRunBudget | None = None,
        transport=None,
        api_key: str | None = None,
    ) -> None:
        self.backend = f"llm:{provider}"
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = LiveModelClient(
            provider=provider, model=model, api_key=api_key, budget=budget, transport=transport
        )
        self._cache: dict[str, JudgeCall] = {}

    def judge(self, request: JudgeRequest) -> JudgeCall:
        key = request.prompt_sha256()
        if key in self._cache:
            cached = self._cache[key]
            return JudgeCall(**{**cached.__dict__, "cache_hit": True})
        result = self.client.complete_messages(
            JUDGE_SYSTEM_PROMPT,
            request.user_message(),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        call = _finish(
            JudgeCall(
                request_sha256=key,
                raw_text=result.text,
                output=None,
                call_error=result.error,
                latency_ms=result.latency_ms,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_usd=result.estimated_cost_usd,
                backend=self.backend,
                model=self.model,
                model_version=result.model_version,
            )
        )
        self._cache[key] = call
        return call


class HeuristicJudge:
    """Offline stand-in: lexical claim/evidence overlap from app.graders. Not an LLM."""

    backend = "heuristic_standin"
    is_llm = False

    def judge(self, request: JudgeRequest) -> JudgeCall:
        started = time.perf_counter()
        evidence = [
            {"chunk_id": item["doc_id"], "text": item["text"], "score": item.get("score", 0.0)}
            for item in request.evidence
        ]
        grade, _ = heuristic_grade(request.prompt, request.response, RequirementSpec(), evidence)
        counts = {c.verdict for c in grade.claims}
        if "contradicted" in counts:
            verdict, category, confidence = "fail", "factual_error", grade.confidence
        elif grade.verdict == "review":
            verdict, category, confidence = "fail", "unsupported_claim", 0.5
        else:
            verdict, category, confidence = "pass", "none", grade.confidence
        payload = {
            "verdict": verdict,
            "failure_category": category,
            "confidence": confidence,
            "reason": grade.reason,
            "claims": [
                {
                    "claim": c.claim,
                    "verdict": "not_verifiable" if c.verdict == "uncertain" else c.verdict,
                    "evidence_ids": c.evidence_chunk_ids,
                }
                for c in grade.claims
            ],
        }
        call = JudgeCall(
            request_sha256=request.prompt_sha256(),
            raw_text=json.dumps(payload, sort_keys=True),
            output=None,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            prompt_tokens=None,
            completion_tokens=None,
            cost_usd=0.0,
            backend=self.backend,
            model="app.graders.heuristic_grade",
        )
        return _finish(call)


class ReplayJudge:
    """Replays raw judge outputs recorded in a previous run; never calls an API."""

    is_llm = True

    def __init__(self, judge_raw_path: Path) -> None:
        self.backend = "replay"
        self.source = str(judge_raw_path)
        self._records: dict[str, dict] = {}
        for line in Path(judge_raw_path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                self._records.setdefault(row["request_sha256"], row)
        backends = {row["backend"] for row in self._records.values()}
        self.is_llm = all(b.startswith("llm:") for b in backends) if backends else False

    def judge(self, request: JudgeRequest) -> JudgeCall:
        key = request.prompt_sha256()
        row = self._records.get(key)
        if row is None:
            return JudgeCall(
                request_sha256=key,
                raw_text="",
                output=None,
                call_error="no recorded judge output for this exact prompt",
                backend=self.backend,
            )
        call = JudgeCall(
            request_sha256=key,
            raw_text=row["raw_text"],
            output=None,
            call_error=row.get("call_error"),
            latency_ms=row.get("latency_ms"),
            prompt_tokens=row.get("prompt_tokens"),
            completion_tokens=row.get("completion_tokens"),
            cost_usd=row.get("cost_usd"),
            backend=f"replay<{row['backend']}>",
            model=row.get("model"),
            model_version=row.get("model_version"),
        )
        return _finish(call)

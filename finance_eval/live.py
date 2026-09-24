"""Live model calling for finance_eval — cost/latency/retry bounded.

Secrets come from environment variables only. CI uses mocked HTTP.
Pricing tables are approximate estimates — labeled as such in evidence.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

import httpx

from finance_eval.schema import FinanceCase

ProviderName = Literal["openai", "anthropic", "mock"]

SYSTEM_PROMPT = (
    "You are being evaluated on finance and accounting tasks. "
    "Follow the user instructions exactly. Prefer concise answers: "
    "numbers only when asked; JSON only when asked; single labels when asked. "
    "Do not invent standards, amounts, or evidence IDs that were not provided."
)

# Approximate USD per 1M tokens — estimates for portfolio cost tracking, not billing.
# Update as needed; always label as estimated in manifests.
PRICE_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "o4-mini": {"input": 1.10, "output": 4.40},
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
    "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "mock-model": {"input": 0.10, "output": 0.10},
}


@dataclass
class ModelCallResult:
    text: str
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost_usd: float | None = None
    error: str | None = None
    retries: int = 0
    provider: str | None = None
    model: str | None = None


class CostCapExceeded(RuntimeError):
    """Raised when cumulative estimated cost exceeds the configured cap."""


class RetryBudgetExceeded(RuntimeError):
    """Raised when per-case retries are exhausted (used internally)."""


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = PRICE_PER_1M.get(model) or {"input": 1.0, "output": 3.0}
    return (prompt_tokens / 1_000_000.0) * rates["input"] + (completion_tokens / 1_000_000.0) * rates["output"]


def build_user_prompt(case: FinanceCase) -> str:
    return (
        f"Case ID: {case.case_id}\n"
        f"Category: {case.category}\n"
        f"Difficulty: {case.difficulty}\n\n"
        f"{case.question}\n"
    )


@dataclass
class LiveRunBudget:
    max_cost_usd: float = 1.0
    max_retries: int = 2
    timeout_s: float = 60.0
    limit: int | None = None
    spent_usd: float = 0.0

    def charge(self, amount: float | None) -> None:
        if amount is None:
            return
        self.spent_usd += amount
        if self.spent_usd > self.max_cost_usd:
            raise CostCapExceeded(
                f"Estimated cost ${self.spent_usd:.4f} exceeds cap ${self.max_cost_usd:.4f}"
            )


class LiveModelClient:
    """Call OpenAI or Anthropic with retry + cost caps.

    maturity: implemented for API shape; live results require user-provided keys.
    """

    def __init__(
        self,
        *,
        provider: ProviderName,
        model: str,
        api_key: str | None = None,
        budget: LiveRunBudget | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider = provider
        self.model = model
        self.budget = budget or LiveRunBudget()
        self.transport = transport
        self.sleep_fn = sleep_fn
        self.api_key = api_key or self._resolve_api_key(provider)
        if provider != "mock" and not self.api_key:
            env = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
            raise RuntimeError(f"{env} is required for provider={provider}")

    @staticmethod
    def _resolve_api_key(provider: ProviderName) -> str | None:
        if provider == "openai":
            return os.getenv("OPENAI_API_KEY") or None
        if provider == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY") or None
        return "mock"

    def complete(self, case: FinanceCase) -> ModelCallResult:
        last_error: str | None = None
        for attempt in range(self.budget.max_retries + 1):
            try:
                result = self._complete_once(case)
                result.retries = attempt
                self.budget.charge(result.estimated_cost_usd)
                return result
            except CostCapExceeded:
                raise
            except Exception as exc:  # noqa: BLE001 — bounded retry surface
                last_error = str(exc)
                if attempt >= self.budget.max_retries:
                    break
                self.sleep_fn(min(2**attempt, 8))
        return ModelCallResult(
            text="",
            error=last_error or "unknown provider error",
            retries=self.budget.max_retries,
            provider=self.provider,
            model=self.model,
        )

    def _complete_once(self, case: FinanceCase) -> ModelCallResult:
        if self.provider == "mock":
            return self._mock_complete(case)
        if self.provider == "openai":
            return self._openai_complete(case)
        if self.provider == "anthropic":
            return self._anthropic_complete(case)
        raise ValueError(f"unsupported provider: {self.provider}")

    def _mock_complete(self, case: FinanceCase) -> ModelCallResult:
        # Deterministic mock for CI — returns gold answer so live path is exerciseable offline.
        text = case.expected_answer
        prompt_tokens = max(8, len(case.question) // 4)
        completion_tokens = max(4, len(text) // 4)
        return ModelCallResult(
            text=text,
            latency_ms=12.0,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=estimate_cost_usd(self.model, prompt_tokens, completion_tokens),
            provider="mock",
            model=self.model,
        )

    def _openai_complete(self, case: FinanceCase) -> ModelCallResult:
        started = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(case)},
            ],
            "temperature": 0,
        }
        with httpx.Client(timeout=self.budget.timeout_s, transport=self.transport) as client:
            res = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
            res.raise_for_status()
            payload = res.json()
        latency_ms = (time.perf_counter() - started) * 1000.0
        text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        return ModelCallResult(
            text=text.strip(),
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=estimate_cost_usd(self.model, prompt_tokens, completion_tokens),
            provider="openai",
            model=self.model,
        )

    def _anthropic_complete(self, case: FinanceCase) -> ModelCallResult:
        started = time.perf_counter()
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": build_user_prompt(case)}],
            "temperature": 0,
        }
        with httpx.Client(timeout=self.budget.timeout_s, transport=self.transport) as client:
            res = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
            res.raise_for_status()
            payload = res.json()
        latency_ms = (time.perf_counter() - started) * 1000.0
        blocks = payload.get("content") or []
        text_parts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(text_parts).strip()
        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("output_tokens") or 0)
        return ModelCallResult(
            text=text,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=estimate_cost_usd(self.model, prompt_tokens, completion_tokens),
            provider="anthropic",
            model=self.model,
        )


def write_redacted_live_summary(path: Any, result: dict[str, Any]) -> None:
    """Write metrics-only summary — never includes model response text."""
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = result.get("manifest") or {}
    payload = {
        "maturity": "live_or_mock_metrics_only",
        "note": "Redacted summary: no prompts, responses, or secrets. Cost is estimated.",
        "run_id": manifest.get("run_id"),
        "model": manifest.get("model"),
        "model_version": manifest.get("model_version"),
        "dataset_version": manifest.get("dataset_version"),
        "dataset_sha256": manifest.get("dataset_sha256"),
        "n_cases": result.get("n_cases"),
        "metrics": result.get("metrics"),
        "policy": result.get("policy"),
        "regression": result.get("regression"),
        "live_budget": result.get("live_budget"),
        "stopped_reason": result.get("stopped_reason"),
    }
    out.write_text(__import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8")

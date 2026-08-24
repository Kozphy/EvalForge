from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    max_tokens: int = 256
    temperature: float = 0.0


@dataclass(frozen=True)
class GenerationResult:
    text: str
    backend: str
    model: str
    status: str = "ok"


class InferenceBackend(Protocol):
    name: str

    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class OllamaBackend:
    name = "ollama"

    def __init__(self, *, model: str, base_url: str = "http://localhost:11434", timeout: float = 60.0) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        response = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return GenerationResult(text=str(data.get("response", "")), backend=self.name, model=self.model)


class OpenAICompatibleBackend:
    """Adapter for vLLM/TGI OpenAI-compatible serving endpoints."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: str = "not-required",
        timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def generate(self, request: GenerationRequest) -> GenerationResult:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"{self.name} returned no choices")
        text = str(choices[0].get("message", {}).get("content", ""))
        return GenerationResult(text=text, backend=self.name, model=self.model)


class UnavailableBackend:
    """Explicitly marks infrastructure that cannot be validated locally."""

    def __init__(self, *, name: str, model: str, reason: str) -> None:
        self.name = name
        self.model = model
        self.reason = reason

    def generate(self, request: GenerationRequest) -> GenerationResult:
        del request
        raise RuntimeError(f"{self.name}/{self.model} is NOT_RUN: {self.reason}")

"""Client API runner: POST evaluation prompts to a configured remote target.

Security notes
--------------
* Only the *name* of an authorization environment variable is stored. Secret
  values are read at request time and never persisted.
* Error messages and stored payloads are scrubbed of known secret values.
* URL validation requires ``http``/``https`` with a hostname. EvalForge is
  local-first and intentionally allows loopback/private addresses for demos.
  Pointing the runner at untrusted networks without egress controls is an
  SSRF risk — document and restrict deployment accordingly.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 120.0
PROMPT_PLACEHOLDER = "{{prompt}}"
_ENV_VAR_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ApiTargetConfig(BaseModel):
    """Per-project remote API target. Never includes secret values."""

    url: str = Field(min_length=1, max_length=2000)
    method: str = "POST"
    body_template: str = Field(min_length=1, max_length=100_000)
    response_field_path: str = Field(min_length=1, max_length=500)
    timeout_seconds: float = Field(
        default=DEFAULT_TIMEOUT_SECONDS,
        gt=0,
        le=MAX_TIMEOUT_SECONDS,
    )
    auth_header: str | None = Field(default="Authorization", max_length=120)
    auth_env_var: str | None = Field(default=None, max_length=120)

    @field_validator("method")
    @classmethod
    def _method_post_only(cls, value: str) -> str:
        if value.upper() != "POST":
            raise ValueError("Only POST is supported for the client API runner.")
        return "POST"

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return validate_api_url(value)

    @field_validator("auth_env_var")
    @classmethod
    def _validate_env_name(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not _ENV_VAR_NAME.match(value):
            raise ValueError("auth_env_var must be a valid environment variable name.")
        return value

    @model_validator(mode="after")
    def _require_prompt_placeholder(self) -> ApiTargetConfig:
        if PROMPT_PLACEHOLDER not in self.body_template:
            raise ValueError(f"body_template must contain {PROMPT_PLACEHOLDER}")
        # Ensure the template is valid JSON once the placeholder is substituted.
        try:
            render_body_template(self.body_template, "validation-probe")
        except ValueError as exc:
            raise ValueError(f"body_template must be valid JSON after substitution: {exc}") from exc
        return self

    def public_dict(self) -> dict[str, Any]:
        """Serialize for API/DB — env var name only, never secret values."""
        return self.model_dump()


class ApiCallResult(BaseModel):
    response_text: str | None = None
    latency_ms: float
    http_status: int | None = None
    error: str | None = None


def validate_api_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https.")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("URL must not embed credentials; use auth_env_var instead.")
    return url.strip()


def render_body_template(template: str, prompt: str) -> dict[str, Any]:
    if PROMPT_PLACEHOLDER not in template:
        raise ValueError(f"body_template must contain {PROMPT_PLACEHOLDER}")
    escaped = json.dumps(prompt, ensure_ascii=False)[1:-1]
    rendered = template.replace(PROMPT_PLACEHOLDER, escaped)
    try:
        payload = json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise ValueError(f"body_template produced invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def extract_field_path(data: Any, path: str) -> str:
    if not path or not path.strip():
        raise ValueError("response_field_path is required.")
    current: Any = data
    for part in path.split("."):
        if part == "":
            raise ValueError(f"Invalid response field path: {path!r}")
        if isinstance(current, dict):
            if part not in current:
                raise ValueError(f"Response field path not found: {path}")
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise ValueError(f"Response field path not found: {path}") from exc
            if index < 0 or index >= len(current):
                raise ValueError(f"Response field path not found: {path}")
            current = current[index]
        else:
            raise ValueError(f"Response field path not found: {path}")
    if current is None:
        raise ValueError(f"Response field path not found: {path}")
    if isinstance(current, (dict, list)):
        return json.dumps(current, ensure_ascii=False)
    return str(current)


def redact_secrets(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def resolve_auth_header(target: ApiTargetConfig) -> tuple[dict[str, str], list[str]]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    secrets: list[str] = []
    if target.auth_env_var:
        value = os.getenv(target.auth_env_var)
        if value:
            header_name = target.auth_header or "Authorization"
            headers[header_name] = value
            secrets.append(value)
        else:
            # Missing env is not fatal here — call site may treat as config error.
            pass
    return headers, secrets


def build_http_client(timeout_seconds: float) -> httpx.Client:
    return httpx.Client(timeout=timeout_seconds)


def call_client_api(
    target: ApiTargetConfig,
    prompt: str,
    *,
    client: httpx.Client | None = None,
) -> ApiCallResult:
    secrets: list[str] = []
    started = time.perf_counter()
    owns_client = client is None
    http = client or build_http_client(target.timeout_seconds)
    try:
        try:
            body = render_body_template(target.body_template, prompt)
            headers, secrets = resolve_auth_header(target)
            if target.auth_env_var and target.auth_env_var not in os.environ:
                latency = (time.perf_counter() - started) * 1000
                return ApiCallResult(
                    latency_ms=round(latency, 2),
                    error=f"Environment variable {target.auth_env_var} is not set.",
                )

            response = http.post(target.url, json=body, headers=headers)
            latency = (time.perf_counter() - started) * 1000
            status = response.status_code
            if status < 200 or status >= 300:
                detail = redact_secrets(response.text[:500], secrets)
                return ApiCallResult(
                    latency_ms=round(latency, 2),
                    http_status=status,
                    error=f"HTTP {status}: {detail or 'non-2xx response'}",
                )
            try:
                payload = response.json()
            except json.JSONDecodeError:
                return ApiCallResult(
                    latency_ms=round(latency, 2),
                    http_status=status,
                    error="Response body is not valid JSON.",
                )
            try:
                text = extract_field_path(payload, target.response_field_path)
            except ValueError as exc:
                return ApiCallResult(
                    latency_ms=round(latency, 2),
                    http_status=status,
                    error=redact_secrets(str(exc), secrets),
                )
            return ApiCallResult(
                response_text=redact_secrets(text, secrets) if secrets else text,
                latency_ms=round(latency, 2),
                http_status=status,
                error=None,
            )
        except httpx.TimeoutException:
            latency = (time.perf_counter() - started) * 1000
            return ApiCallResult(
                latency_ms=round(latency, 2),
                error="Request timed out waiting for the client API.",
            )
        except httpx.HTTPError as exc:
            latency = (time.perf_counter() - started) * 1000
            return ApiCallResult(
                latency_ms=round(latency, 2),
                error=redact_secrets(f"HTTP client error: {exc}", secrets),
            )
        except ValueError as exc:
            latency = (time.perf_counter() - started) * 1000
            return ApiCallResult(
                latency_ms=round(latency, 2),
                error=redact_secrets(str(exc), secrets),
            )
    finally:
        if owns_client:
            http.close()

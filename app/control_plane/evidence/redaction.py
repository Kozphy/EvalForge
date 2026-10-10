"""Secret redaction before evidence persistence."""

from __future__ import annotations

import copy
import os
import re
from typing import Any

SECRET_ENV_HINTS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "AUTHORIZATION",
    "AUTH",
    "CREDENTIAL",
)

_BEARER = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]+)")


def collect_secret_values(extra: list[str] | None = None) -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        upper = key.upper()
        if any(hint in upper for hint in SECRET_ENV_HINTS) and value:
            values.append(value)
    if extra:
        values.extend(v for v in extra if v)
    # Longest first to avoid partial masking issues
    return sorted(set(values), key=len, reverse=True)


def redact_text(text: str, secrets: list[str] | None = None) -> str:
    secrets = secrets if secrets is not None else collect_secret_values()
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _BEARER.sub(r"\1[REDACTED]", redacted)
    return redacted


def redact_structure(data: Any, secrets: list[str] | None = None) -> Any:
    secrets = secrets if secrets is not None else collect_secret_values()
    if isinstance(data, str):
        return redact_text(data, secrets)
    if isinstance(data, list):
        return [redact_structure(item, secrets) for item in data]
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            key_upper = str(key).upper()
            if any(hint in key_upper for hint in ("AUTHORIZATION", "API_KEY", "TOKEN", "PASSWORD", "SECRET")):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_structure(value, secrets)
        return out
    return copy.deepcopy(data)

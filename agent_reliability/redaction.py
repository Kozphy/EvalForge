"""Redact secrets and high-entropy tokens from audit text."""

from __future__ import annotations

import os
import re

_BEARER = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)\S+")
_KEY_ASSIGN = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|authorization)\b(\s*[:=]\s*)(\S+)"
)


def collect_secret_values(extra: list[str] | None = None) -> list[str]:
    secrets: list[str] = []
    for key, value in os.environ.items():
        upper = key.upper()
        if any(h in upper for h in ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION")):
            if value and len(value) >= 8:
                secrets.append(value)
    if extra:
        secrets.extend(s for s in extra if s)
    # Longest first so partial overlaps redact fully.
    return sorted(set(secrets), key=len, reverse=True)


def redact_text(text: str, extra_secrets: list[str] | None = None) -> tuple[str, list[str]]:
    applied: list[str] = []
    redacted = text
    for secret in collect_secret_values(extra_secrets):
        if secret and secret in redacted:
            redacted = redacted.replace(secret, "[REDACTED]")
            applied.append("env_or_provided_secret")
    if _BEARER.search(redacted):
        redacted = _BEARER.sub(r"\1[REDACTED]", redacted)
        applied.append("bearer_header")
    if _KEY_ASSIGN.search(redacted):
        redacted = _KEY_ASSIGN.sub(r"\1\2[REDACTED]", redacted)
        applied.append("key_assignment")
    return redacted, sorted(set(applied))

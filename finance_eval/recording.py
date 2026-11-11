"""Provider-run evidence recording and offline replay.

A *run record* is the minimum evidence needed to claim "model X produced
these outputs on dataset Y": who was called, with what exact prompt, what
came back, and what it cost. Records are JSONL (one call per line) plus a
header line, and the file's sha256 goes into the evidence manifest.

Replay re-grades a recorded run without any network access. Replayed runs
are always labelled ``replayed_from=<record sha256>`` so they can never be
mistaken for a fresh live call.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

RECORD_SCHEMA_VERSION = "finance_eval.run_record/v1"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001 — best effort provenance
        return None


class RunHeader(BaseModel):
    record_type: Literal["header"] = "header"
    schema_version: str = RECORD_SCHEMA_VERSION
    run_id: str
    started_at_utc: str
    provider: str
    model: str
    model_digest: Optional[str] = Field(None, description="e.g. Ollama model digest; required for local models")
    endpoint_host: str
    is_local: bool
    paid: bool
    temperature: float
    seed: Optional[int]
    max_output_tokens: int
    system_prompt_sha256: str
    prompt_version: str
    dataset_version: str
    dataset_sha256: str
    max_cost_usd: float
    limit: Optional[int]
    git_commit: Optional[str] = None
    python: str = Field(default_factory=platform.python_version)


class CallRecord(BaseModel):
    record_type: Literal["call"] = "call"
    case_id: str
    prompt_sha256: str
    response_text: str
    response_sha256: str
    latency_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    provider_request_id: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    recorded_at_utc: str


class RunRecorder:
    """Append-only writer for one provider run."""

    def __init__(self, path: Path, header: RunHeader) -> None:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite run record {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if header.git_commit is None:
            header = header.model_copy(update={"git_commit": _git_commit()})
        self.path = path
        self.header = header
        self._fh = path.open("w", encoding="utf-8")
        self._write(header.model_dump())

    def _write(self, row: dict[str, Any]) -> None:
        self._fh.write(json.dumps(row, sort_keys=True) + "\n")
        self._fh.flush()

    def record(self, *, case_id: str, prompt: str, response_text: str, **fields: Any) -> CallRecord:
        rec = CallRecord(
            case_id=case_id,
            prompt_sha256=sha256_text(prompt),
            response_text=response_text,
            response_sha256=sha256_text(response_text),
            recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            **fields,
        )
        self._write(rec.model_dump())
        return rec

    def close(self) -> str:
        self._fh.close()
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def load_record(path: Path) -> tuple[RunHeader, dict[str, CallRecord], str]:
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or lines[0].get("record_type") != "header":
        raise ValueError(f"{path}: first line must be a run header")
    header = RunHeader(**lines[0])
    calls: dict[str, CallRecord] = {}
    for row in lines[1:]:
        rec = CallRecord(**row)
        if rec.response_sha256 != sha256_text(rec.response_text):
            raise ValueError(f"{path}: response hash mismatch for {rec.case_id}")
        calls[rec.case_id] = rec
    return header, calls, hashlib.sha256(path.read_bytes()).hexdigest()

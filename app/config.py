"""Grader / run configuration snapshots and environment helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from .version import APP_VERSION

# Import limits (overridable via environment)
MAX_IMPORT_CASES = int(os.getenv("EVAL_MAX_IMPORT_CASES", "10000"))
MAX_IMPORT_FILE_BYTES = int(os.getenv("EVAL_MAX_IMPORT_FILE_BYTES", str(20 * 1024 * 1024)))
ALLOWED_IMPORT_EXTENSIONS = frozenset({".jsonl", ".csv"})


class GraderConfig(BaseModel):
    """Immutable evaluation configuration recorded with each run."""

    provider: str
    model: str
    model_version: str | None = None
    prompt_version: str = "1"
    system_prompt: str | None = None
    grader_prompt: str | None = None
    temperature: float = 0.0
    max_output_tokens: int | None = None
    retrieval_method: str = "tfidf"
    retrieval_top_k: int = 5
    evidence_threshold: float = 0.25
    rule_set_version: str = "1"
    dataset_version: str | None = None
    git_commit_sha: str | None = None
    app_version: str = APP_VERSION
    # Public API-target snapshot (env var *name* only — never secret values).
    api_target: dict | None = None


def detect_git_commit_sha(cwd: Path | None = None) -> str | None:
    """Return the current Git commit SHA, or None if unavailable.

    When ``cwd`` is provided explicitly, require a ``.git`` entry in that
    directory so temporary folders nested inside a checkout are not treated
    as the application repository.
    """
    root = cwd or Path.cwd()
    if cwd is not None and not (Path(cwd) / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = (result.stdout or "").strip()
    return sha or None


def build_grader_config(
    *,
    provider: str,
    model: str,
    top_k: int,
    dataset_version: str | None = None,
    prompt_version: str = "1",
    system_prompt: str | None = None,
    grader_prompt: str | None = None,
    temperature: float = 0.0,
    max_output_tokens: int | None = None,
    evidence_threshold: float = 0.25,
    rule_set_version: str = "1",
    model_version: str | None = None,
    api_target: dict | None = None,
) -> GraderConfig:
    return GraderConfig(
        provider=provider,
        model=model,
        model_version=model_version,
        prompt_version=prompt_version,
        system_prompt=system_prompt,
        grader_prompt=grader_prompt,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        retrieval_method="tfidf",
        retrieval_top_k=top_k,
        evidence_threshold=evidence_threshold,
        rule_set_version=rule_set_version,
        dataset_version=dataset_version,
        git_commit_sha=detect_git_commit_sha(),
        app_version=APP_VERSION,
        api_target=api_target,
    )

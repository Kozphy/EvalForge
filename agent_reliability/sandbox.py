"""Local subprocess sandbox for fixture tests — no network, no merge."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from agent_reliability.interface_v1 import SandboxTestResult
from agent_reliability.redaction import redact_text

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "demo_pkg"


def materialize_workspace(patch_text: str | None = None) -> Path:
    """Copy the demo package into a temp workspace and optionally replace calc.py."""
    root = Path(tempfile.mkdtemp(prefix="arp_sandbox_"))
    dest = root / "demo_pkg"
    shutil.copytree(FIXTURES, dest)
    if patch_text is not None and patch_text.strip():
        if patch_text.lstrip().startswith("diff ") or "\n--- " in patch_text[:200]:
            raise ValueError("unified diffs are not applied in the local fixture sandbox")
        (dest / "calc.py").write_text(patch_text, encoding="utf-8")
    return root


def _sandbox_env(workspace: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(workspace)
    return env


def run_pytest(workspace: Path, *, timeout_s: float = 30.0) -> SandboxTestResult:
    cmd = [sys.executable, "-m", "pytest", "-q", str(workspace / "demo_pkg" / "tests")]
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=_sandbox_env(workspace),
        )
    except subprocess.TimeoutExpired as exc:
        out, _ = redact_text(exc.stdout if isinstance(exc.stdout, str) else "")
        err, _ = redact_text(exc.stderr if isinstance(exc.stderr, str) else "")
        return SandboxTestResult(
            passed=False,
            exit_code=124,
            duration_ms=(time.perf_counter() - started) * 1000,
            command=cmd,
            stdout_redacted=out,
            stderr_redacted=err,
            error="sandbox_timeout",
        )

    stdout, _ = redact_text(proc.stdout or "")
    stderr, _ = redact_text(proc.stderr or "")
    return SandboxTestResult(
        passed=proc.returncode == 0,
        exit_code=proc.returncode,
        duration_ms=(time.perf_counter() - started) * 1000,
        command=cmd,
        stdout_redacted=stdout,
        stderr_redacted=stderr,
        error=None if proc.returncode == 0 else "pytest_failed",
    )


def cleanup_workspace(workspace: Path) -> None:
    shutil.rmtree(workspace, ignore_errors=True)

"""Regression tests for reference-label metrics and mock-run output location.

Numeric expectations are tied to the pinned finance-accounting-v1 dataset (sha256 enforced on
load). If the dataset is bumped, recompute them from the dataset rather than from grader output.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from finance_eval import __main__ as cli
from finance_eval import runner
from finance_eval.runner import DEFAULT_LIVE_SUMMARY, DEFAULT_MOCK_LIVE_SUMMARY, run_evaluation

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path: Path, **kwargs):
    return run_evaluation(
        evidence_dir=tmp_path / "ev",
        reviews_path=tmp_path / "reviews.jsonl",
        baseline_path=None,
        seed_reviews=False,
        **kwargs,
    )


def test_candidate_metrics_use_planted_labels_not_grader_output(tmp_path: Path) -> None:
    metrics = _run(tmp_path, mode="candidate")["metrics"]
    # 122 clean cases graded PASS (TP); PY-015 is planted but graded PASS (FP);
    # 31 planted cases graded FAIL (TN); no clean case graded FAIL (FN = 0). PASS is positive.
    assert metrics["n_passed"] == 123
    assert metrics["precision"] == pytest.approx(122 / 123)
    assert metrics["recall"] == pytest.approx(1.0)
    assert metrics["f1"] == pytest.approx(2 * (122 / 123) / (122 / 123 + 1))
    assert metrics["false_positive_rate"] == pytest.approx(1 / 32)
    assert metrics["precision"] < 1.0  # the old self-comparison always produced 1.0
    assert "planted_failure" in metrics["reference_label_source"]


def test_gold_metrics_label_every_expected_answer_as_should_pass(tmp_path: Path) -> None:
    metrics = _run(tmp_path, mode="gold")["metrics"]
    assert metrics["precision"] == metrics["recall"] == metrics["f1"] == pytest.approx(1.0)
    assert metrics["false_positive_rate"] is None  # no should-fail cases in gold mode
    assert metrics["reference_label_source"] == runner.GOLD_LABEL_SOURCE


def test_custom_response_fn_has_no_reference_labels(tmp_path: Path) -> None:
    metrics = _run(tmp_path, response_fn=lambda case: case.expected_answer, limit=5)["metrics"]
    assert metrics["precision"] is None
    assert metrics["recall"] is None
    assert metrics["f1"] is None
    assert metrics["reference_label_source"] is None


def test_mock_default_summary_is_not_the_tracked_example() -> None:
    assert DEFAULT_MOCK_LIVE_SUMMARY != DEFAULT_LIVE_SUMMARY
    assert DEFAULT_MOCK_LIVE_SUMMARY.parent.name == "output"


def test_mock_default_summary_location_is_gitignored() -> None:
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("git checkout not available")
    rel = DEFAULT_MOCK_LIVE_SUMMARY.relative_to(REPO_ROOT).as_posix()
    check = subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO_ROOT)
    assert check.returncode == 0, f"{rel} must be gitignored"


def _tracked_status() -> str | None:
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        return None
    return subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout


def test_mock_cli_run_leaves_tracked_files_unchanged(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mock_summary = tmp_path / "mock_summary.json"
    monkeypatch.setattr(cli, "DEFAULT_MOCK_LIVE_SUMMARY", mock_summary)
    example_before = DEFAULT_LIVE_SUMMARY.read_bytes()
    status_before = _tracked_status()

    code = cli.main([
        "run", "--mode", "live", "--provider", "mock", "--limit", "3",
        "--max-cost-usd", "1", "--evidence-dir", str(tmp_path / "ev"),
        "--baseline", str(tmp_path / "no_baseline.json"),
    ])
    capsys.readouterr()

    assert code == 0
    assert mock_summary.exists()
    assert DEFAULT_LIVE_SUMMARY.read_bytes() == example_before
    if status_before is not None:
        assert _tracked_status() == status_before


def test_cli_fails_closed_on_tampered_dataset_copy(tmp_path: Path, capsys) -> None:
    data_dir = tmp_path / "dataset"
    data_dir.mkdir()
    src = runner.DEFAULT_DATASET
    shutil.copy(src, data_dir / src.name)
    shutil.copy(src.with_name("MANIFEST.json"), data_dir / "MANIFEST.json")
    tampered = data_dir / src.name
    tampered.write_bytes(tampered.read_bytes().replace(b"EQ-001", b"EQ-00X", 1))

    code = cli.main([
        "run", "--mode", "candidate", "--dataset", str(tampered),
        "--baseline", str(tmp_path / "baseline.json"), "--write-baseline",
        "--evidence-dir", str(tmp_path / "ev"),
    ])
    err = capsys.readouterr().err

    assert code == 2
    assert "SHA-256 does not match MANIFEST.json" in err
    assert not (tmp_path / "ev").exists()
    assert not (tmp_path / "baseline.json").exists()

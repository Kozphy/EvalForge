from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from finance_eval import DATASET_VERSION
from finance_eval.metrics import aggregate_metrics
from finance_eval.runner import load_dataset, run_evaluation
from finance_eval.schema import CaseResult, FinanceCase


def _results() -> list[CaseResult]:
    return [
        CaseResult(case_id=str(i), category="accounting_equations", difficulty="easy",
                   passed=passed, score=float(passed))
        for i, passed in enumerate([True, True, False, False, False])
    ]


def test_no_reference_means_unavailable_not_perfect() -> None:
    metrics = aggregate_metrics(_results())
    assert metrics.accuracy == pytest.approx(0.4)
    assert metrics.precision is None
    assert metrics.recall is None
    assert metrics.f1 is None
    assert metrics.false_positive_rate is None


def test_independent_reference_known_confusion_matrix() -> None:
    # Hand-specified unit-test labels, not a claim of real independent human review.
    labels = dict(zip([str(i) for i in range(5)], [True, False, True, False, True]))
    metrics = aggregate_metrics(_results(), reference_pass=labels)
    assert metrics.precision == pytest.approx(0.5)  # TP=1 FP=1
    assert metrics.recall == pytest.approx(1 / 3)  # FN=2
    assert metrics.f1 == pytest.approx(0.4)
    assert metrics.false_positive_rate == pytest.approx(0.5)  # TN=1


@pytest.mark.parametrize("labels", [{}, {"0": True}, {str(i): "pass" for i in range(5)}])
def test_bad_reference_labels_are_rejected(labels) -> None:
    with pytest.raises(ValueError):
        aggregate_metrics(_results(), reference_pass=labels)


def test_duplicate_result_ids_rejected_with_reference() -> None:
    row = _results()[0]
    with pytest.raises(ValueError, match="duplicate"):
        aggregate_metrics([row, row], reference_pass={"0": True})


def test_zero_true_positives_is_zero_not_missing_f1() -> None:
    rows = _results()[:2]
    rows[1].passed = False
    metrics = aggregate_metrics(rows, reference_pass={"0": False, "1": True})
    assert metrics.precision == metrics.recall == metrics.f1 == 0.0


def _dataset(tmp_path: Path) -> Path:
    case = FinanceCase.model_validate({
        "case_id": "HASH-001", "dataset_version": DATASET_VERSION,
        "category": "accounting_equations", "difficulty": "easy", "question": "q",
        "expected_answer": "60", "candidate_response": "60",
        "structured_golden": {"mode": "numeric", "value": 60},
        "grading_rubric": {"correct_if": "60", "fail_if": "other"},
    })
    path = tmp_path / "cases.jsonl"
    path.write_bytes((case.model_dump_json() + "\n").encode("utf-8"))
    _manifest(path)
    return path


def _manifest(path: Path, **changes) -> None:
    manifest = {
        "dataset_version": DATASET_VERSION, "n_cases": 1,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    manifest.update(changes)
    path.with_name("MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_manifest_verifies_and_run_records_exact_snapshot(tmp_path: Path) -> None:
    path = _dataset(tmp_path)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(load_dataset(path)) == 1

    def replace_after_validation(case):
        path.write_bytes(b"changed after validation")
        return case.expected_answer

    result = run_evaluation(dataset_path=path, response_fn=replace_after_validation,
                            evidence_dir=tmp_path / "ev", reviews_path=tmp_path / "reviews",
                            baseline_path=None, seed_reviews=False)
    assert result["manifest"]["dataset_sha256"] == expected
    assert result["n_cases"] == 1


def test_changed_byte_rejected_before_response_or_evidence(tmp_path: Path) -> None:
    path = _dataset(tmp_path)
    path.write_bytes(path.read_bytes() + b" ")
    calls = []
    with pytest.raises(ValueError, match="SHA-256"):
        run_evaluation(dataset_path=path, response_fn=lambda case: calls.append(case) or "60",
                       evidence_dir=tmp_path / "ev", reviews_path=tmp_path / "reviews",
                       baseline_path=None, seed_reviews=False)
    assert calls == []
    assert not (tmp_path / "ev").exists()
    assert not (tmp_path / "reviews").exists()


@pytest.mark.parametrize("content", [None, "{broken", "[]"])
def test_missing_or_malformed_manifest_fails_closed(tmp_path: Path, content) -> None:
    path = _dataset(tmp_path)
    manifest = path.with_name("MANIFEST.json")
    if content is None:
        manifest.unlink()
    else:
        manifest.write_text(content, encoding="utf-8")
    with pytest.raises((FileNotFoundError, ValueError)):
        load_dataset(path)


@pytest.mark.parametrize("changes", [{"n_cases": 2}, {"n_cases": True}, {"dataset_version": "wrong"}])
def test_manifest_count_and_version_checked(tmp_path: Path, changes) -> None:
    path = _dataset(tmp_path)
    _manifest(path, **changes)
    with pytest.raises(ValueError):
        load_dataset(path)


def test_duplicate_case_ids_rejected_even_with_matching_hash(tmp_path: Path) -> None:
    path = _dataset(tmp_path)
    path.write_bytes(path.read_bytes() * 2)
    _manifest(path, n_cases=2)
    with pytest.raises(ValueError, match="duplicate"):
        load_dataset(path)

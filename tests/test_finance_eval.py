from __future__ import annotations

import json
from pathlib import Path

import pytest

from finance_eval.evidence import sha256_file
from finance_eval.generate_dataset import write_dataset
from finance_eval.graders import grade_case
from finance_eval.metrics import aggregate_metrics, planted_detection_counts
from finance_eval.policy import evaluate_policy
from finance_eval.runner import (
    DEFAULT_DATASET,
    DEFAULT_MANIFEST,
    DatasetIntegrityError,
    load_dataset,
    run_evaluation,
    verify_dataset_integrity,
)
from finance_eval.schema import CaseResult, FinanceCase, RunMetrics
from finance_eval.taxonomy import FinanceFailureCode, taxonomy_catalog


def test_dataset_size_and_manifest(tmp_path: Path, monkeypatch) -> None:
    # Regenerate into package dataset (idempotent) then validate
    manifest = write_dataset()
    assert 100 <= manifest["n_cases"] <= 200
    assert manifest["sha256"]
    assert sum(manifest["categories"].values()) == manifest["n_cases"]
    dataset = Path("finance_eval/dataset/finance_accounting_v1.jsonl")
    assert dataset.exists()
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(cases) == manifest["n_cases"]
    required = {
        "case_id",
        "category",
        "question",
        "expected_answer",
        "structured_golden",
        "grading_rubric",
        "known_failure_modes",
        "candidate_response",
    }
    assert required.issubset(cases[0].keys())


def test_deterministic_grades_numeric_and_journal() -> None:
    eq = FinanceCase.model_validate(
        {
            "case_id": "T-EQ",
            "dataset_version": "finance-accounting-v1",
            "category": "accounting_equations",
            "difficulty": "easy",
            "question": "q",
            "expected_answer": "60",
            "structured_golden": {"mode": "numeric", "value": 60.0, "tolerance": 0.01},
            "grading_rubric": {"correct_if": "x", "fail_if": "y"},
            "candidate_response": "60",
            "planted_failure": "FIN-NONE",
        }
    )
    assert grade_case(eq, "60")["passed"] is True
    assert grade_case(eq, "59")["passed"] is False

    je = FinanceCase.model_validate(
        {
            "case_id": "T-JE",
            "dataset_version": "finance-accounting-v1",
            "category": "journal_entries",
            "difficulty": "medium",
            "question": "q",
            "expected_answer": "{}",
            "structured_golden": {
                "mode": "journal_json",
                "value": {
                    "debits": [{"account": "Cash", "amount": 100}],
                    "credits": [{"account": "Revenue", "amount": 100}],
                },
                "tolerance": 0.01,
            },
            "grading_rubric": {"correct_if": "x", "fail_if": "y"},
            "candidate_response": "{}",
            "planted_failure": "FIN-NONE",
        }
    )
    good = '{"debits":[{"account":"Cash","amount":100}],"credits":[{"account":"Revenue","amount":100}]}'
    bad = '{"debits":[{"account":"Cash","amount":100}],"credits":[{"account":"Revenue","amount":50}]}'
    assert grade_case(je, good)["passed"] is True
    assert FinanceFailureCode.FIN_JE_011.value in grade_case(je, bad)["failure_codes"]


def test_taxonomy_machine_readable() -> None:
    catalog = taxonomy_catalog()
    assert any(item["code"] == "FIN-CALC-001" for item in catalog)
    assert all("description" in item for item in catalog)


def test_policy_fail_on_critical_errors() -> None:
    metrics = RunMetrics(
        n_cases=100,
        n_passed=90,
        accuracy=0.9,
        pass_rate=0.9,
        hallucination_rate=0.0,
        calculation_error_rate=0.0,
        reasoning_error_rate=0.0,
        citation_evidence_failure_rate=0.0,
        instruction_following_failure_rate=0.0,
        critical_error_rate=0.08,
        failure_counts={"FIN-AUD-004": 8},
    )
    decision = evaluate_policy(metrics)
    assert decision["decision"] == "FAIL"


def test_policy_human_review_on_hallucination() -> None:
    metrics = RunMetrics(
        n_cases=100,
        n_passed=90,
        accuracy=0.9,
        pass_rate=0.9,
        hallucination_rate=0.05,
        calculation_error_rate=0.0,
        reasoning_error_rate=0.0,
        citation_evidence_failure_rate=0.0,
        instruction_following_failure_rate=0.0,
        critical_error_rate=0.01,
        failure_counts={"FIN-HALL-006": 5},
    )
    decision = evaluate_policy(metrics)
    assert decision["decision"] == "HUMAN_REVIEW_REQUIRED"


def test_verify_dataset_integrity_accepts_pinned_golden_set() -> None:
    write_dataset()
    record = verify_dataset_integrity(DEFAULT_DATASET)
    assert record["verified"] is True
    assert record["dataset_sha256"] == sha256_file(DEFAULT_DATASET)
    pinned = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert record["dataset_sha256"] == pinned["sha256"]


def test_runner_refuses_tampered_dataset(tmp_path: Path) -> None:
    write_dataset()
    pinned = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    tampered = tmp_path / "finance_accounting_v1.jsonl"
    tampered.write_bytes(DEFAULT_DATASET.read_bytes() + b"\n")
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({**pinned, "sha256": pinned["sha256"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetIntegrityError, match="sha256 does not match"):
        run_evaluation(
            dataset_path=tampered,
            evidence_dir=tmp_path / "evidence",
            reviews_path=tmp_path / "reviews.jsonl",
            baseline_path=None,
            seed_reviews=False,
            mode="candidate",
            limit=1,
        )


def test_runner_refuses_unpinned_dataset(tmp_path: Path) -> None:
    write_dataset()
    copy = tmp_path / "orphan.jsonl"
    copy.write_bytes(DEFAULT_DATASET.read_bytes())
    with pytest.raises(DatasetIntegrityError, match="No MANIFEST.json"):
        run_evaluation(
            dataset_path=copy,
            evidence_dir=tmp_path / "evidence",
            reviews_path=tmp_path / "reviews.jsonl",
            baseline_path=None,
            seed_reviews=False,
            mode="gold",
            limit=1,
        )


def test_runner_records_dataset_integrity_in_evidence(tmp_path: Path) -> None:
    write_dataset()
    result = run_evaluation(
        evidence_dir=tmp_path / "evidence",
        reviews_path=tmp_path / "reviews.jsonl",
        baseline_path=None,
        seed_reviews=False,
        mode="gold",
        limit=3,
    )
    integrity = result["manifest"]["dataset_integrity"]
    assert integrity["verified"] is True
    assert integrity["dataset_sha256"] == sha256_file(DEFAULT_DATASET)


def test_detection_metrics_null_without_planted_labels() -> None:
    results = [
        CaseResult(
            case_id="A",
            category="accounting_equations",
            difficulty="easy",
            passed=True,
            score=1.0,
            failure_codes=["FIN-NONE"],
        ),
        CaseResult(
            case_id="B",
            category="accounting_equations",
            difficulty="easy",
            passed=False,
            score=0.0,
            failure_codes=["FIN-CALC-001"],
        ),
    ]
    metrics = aggregate_metrics(results, compute_planted_detection=False)
    assert metrics.precision is None
    assert metrics.recall is None
    assert metrics.f1 is None
    assert metrics.false_positive_rate is None
    assert planted_detection_counts(results) is None


def test_detection_metrics_against_planted_labels() -> None:
    results = [
        CaseResult(
            case_id="clean-pass",
            category="accounting_equations",
            difficulty="easy",
            passed=True,
            score=1.0,
            failure_codes=["FIN-NONE"],
            planted_failure="FIN-NONE",
        ),
        CaseResult(
            case_id="planted-caught",
            category="accounting_equations",
            difficulty="easy",
            passed=False,
            score=0.0,
            failure_codes=["FIN-CALC-001"],
            planted_failure="FIN-ACC-002",
        ),
        CaseResult(
            case_id="planted-miss",
            category="python_financial",
            difficulty="hard",
            passed=True,
            score=1.0,
            failure_codes=["FIN-NONE"],
            planted_failure="FIN-PY-008",
        ),
        CaseResult(
            case_id="false-alarm",
            category="accounting_equations",
            difficulty="easy",
            passed=False,
            score=0.0,
            failure_codes=["FIN-CALC-001"],
            planted_failure="FIN-NONE",
        ),
    ]
    assert planted_detection_counts(results) == (1, 1, 1, 1)
    metrics = aggregate_metrics(results, compute_planted_detection=True)
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f1 == 0.5
    assert metrics.false_positive_rate == 0.5


def test_candidate_run_reports_planted_detection(tmp_path: Path) -> None:
    write_dataset()
    evidence = tmp_path / "evidence"
    reviews = tmp_path / "reviews.jsonl"
    candidate = run_evaluation(
        evidence_dir=evidence,
        reviews_path=reviews,
        baseline_path=None,
        seed_reviews=False,
        mode="candidate",
    )
    metrics = candidate["metrics"]
    cases = load_dataset()
    planted = [c for c in cases if c.planted_failure != "FIN-NONE"]
    clean = [c for c in cases if c.planted_failure == "FIN-NONE"]
    assert len(planted) == 32
    assert len(clean) == 122
    # Detection metrics are defined (not tautological 1.0/1.0 from self-compare).
    assert metrics["precision"] is not None
    assert metrics["recall"] is not None
    assert metrics["false_positive_rate"] is not None
    # Documented verification: 31/32 planted caught, 0 false alarms on clean cases.
    assert metrics["recall"] == 31 / 32
    assert metrics["false_positive_rate"] == 0.0
    assert metrics["precision"] == 1.0
    # Gold / non-candidate path must not invent detection rates.
    gold = run_evaluation(
        evidence_dir=evidence,
        reviews_path=reviews,
        baseline_path=None,
        seed_reviews=False,
        mode="gold",
    )
    assert gold["metrics"]["precision"] is None
    assert gold["metrics"]["recall"] is None
    assert gold["metrics"]["f1"] is None
    assert gold["metrics"]["false_positive_rate"] is None


def test_end_to_end_offline_pipeline(tmp_path: Path) -> None:
    write_dataset()
    evidence = tmp_path / "evidence"
    reviews = tmp_path / "reviews.jsonl"
    baseline = tmp_path / "baseline.json"
    gold = run_evaluation(
        evidence_dir=evidence,
        reviews_path=reviews,
        baseline_path=baseline,
        write_baseline=True,
        seed_reviews=False,
        mode="gold",
    )
    assert gold["metrics"]["accuracy"] >= 0.95
    assert gold["policy"]["decision"] in {"PASS", "WARN"}
    candidate = run_evaluation(
        evidence_dir=evidence,
        reviews_path=reviews,
        baseline_path=baseline,
        write_baseline=False,
        seed_reviews=True,
        mode="candidate",
    )
    assert candidate["n_cases"] >= 100
    assert candidate["metrics"]["accuracy"] < gold["metrics"]["accuracy"]
    assert candidate["regression"] is not None
    assert candidate["policy"]["decision"] in {"PASS", "WARN", "FAIL", "HUMAN_REVIEW_REQUIRED"}
    assert list(evidence.glob("*.manifest.json"))

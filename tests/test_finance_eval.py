from __future__ import annotations

import json
from pathlib import Path

from finance_eval.generate_dataset import write_dataset
from finance_eval.graders import grade_case
from finance_eval.policy import evaluate_policy
from finance_eval.runner import run_evaluation
from finance_eval.schema import FinanceCase, RunMetrics
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

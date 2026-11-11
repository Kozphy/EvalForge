import json
from pathlib import Path

import pytest

from finance_eval.human_review import ReviewProvenanceError, load_reviews, seed_demo_reviews
from finance_eval.runner import load_dataset, run_evaluation


def _write(path: Path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_seed_rows_are_not_human(tmp_path):
    rows = seed_demo_reviews([{"case_id": "a", "passed": True}, {"case_id": "b", "passed": False}], tmp_path / "r.jsonl")
    assert {r["source"] for r in rows} == {"seeded_demo"}
    assert all(r["seeded"] is True and "@" not in r["reviewer"] for r in rows)


def test_default_run_does_not_seed(tmp_path):
    out = run_evaluation(evidence_dir=tmp_path / "ev", reviews_path=tmp_path / "r.jsonl", baseline_path=None)
    assert not (tmp_path / "r.jsonl").exists()
    assert out["manifest"]["human_review_status"] == "NONE"
    assert out["judge_human_agreement"] is None


def test_seeded_run_reports_zero_human_reviews(tmp_path):
    out = run_evaluation(evidence_dir=tmp_path / "ev", reviews_path=tmp_path / "r.jsonl", baseline_path=None, seed_reviews=True)
    assert out["n_human_reviews"] == 0
    assert out["n_seeded_demo_reviews"] == 20
    assert out["judge_human_agreement"] is None
    assert out["manifest"]["human_review_status"] == "SEEDED_DEMO_ONLY_NO_HUMAN_REVIEW"


def test_real_reviews_are_never_overwritten(tmp_path):
    case_id = load_dataset()[0].case_id
    path = tmp_path / "r.jsonl"
    _write(path, [{"case_id": case_id, "reviewer": "rater_01", "source": "human_independent", "decision": "fail"}])
    with pytest.raises(FileExistsError):
        run_evaluation(evidence_dir=tmp_path / "ev", reviews_path=path, baseline_path=None, seed_reviews=True)
    assert json.loads(path.read_text())["reviewer"] == "rater_01"


def test_independent_reviews_counted_and_used(tmp_path):
    cases = load_dataset()[:2]
    path = tmp_path / "r.jsonl"
    _write(path, [{"case_id": c.case_id, "reviewer": f"rater_{i}", "source": "human_independent", "decision": "pass"} for i, c in enumerate(cases)])
    out = run_evaluation(evidence_dir=tmp_path / "ev", reviews_path=path, baseline_path=None)
    assert out["n_human_reviews"] == 2
    assert out["manifest"]["human_review_status"] == "INDEPENDENT_PARTIAL"


@pytest.mark.parametrize("reviewer", ["human.reviewer@example.com", "", "seed-script (not a person)"])
def test_placeholder_reviewer_cannot_claim_human(tmp_path, reviewer):
    path = tmp_path / "r.jsonl"
    _write(path, [{"case_id": "x", "reviewer": reviewer, "source": "human_independent", "decision": "pass"}])
    with pytest.raises(ReviewProvenanceError):
        load_reviews(path)

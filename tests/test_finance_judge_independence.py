from pathlib import Path

import pytest

from finance_eval.judge import attach_judge, heuristic_judge, judge_is_independent
from finance_eval.runner import load_dataset, run_evaluation
from finance_eval.schema import CaseResult


def _result(case, passed):
    return CaseResult(case_id=case.case_id, category=case.category, difficulty=case.difficulty,
                      passed=passed, score=1.0 if passed else 0.0, failure_codes=[], deterministic_detail={})


def test_heuristic_judge_is_flagged_as_mirror():
    case = load_dataset()[0]
    j = heuristic_judge(case, "anything", {"passed": True, "failure_codes": []})
    assert j["independent"] is False
    assert j["derived_from"] == "deterministic_grader"
    assert judge_is_independent(j) is False


def test_mirror_judge_agreement_not_reported(tmp_path: Path):
    out = run_evaluation(evidence_dir=tmp_path / "ev", reviews_path=tmp_path / "r.jsonl", baseline_path=None)
    assert out["judge_independent"] is False
    assert out["judge_human_agreement"] is None
    assert "not independent" in out["judge_human_agreement_note"]


def test_independent_judge_never_sees_grader_and_enables_agreement(tmp_path: Path):
    seen = []

    def judge(case, response):
        seen.append((case.case_id, response))
        return {"source": "test_stub_judge", "decision": "pass"}

    import json
    reviews = tmp_path / "r.jsonl"
    reviews.write_text("".join(json.dumps({"case_id": c.case_id, "reviewer": f"rater_{i}", "source": "human_independent",
                                           "decision": "pass"}) + "\n" for i, c in enumerate(load_dataset()[:20])))
    out = run_evaluation(evidence_dir=tmp_path / "ev", reviews_path=reviews,
                         baseline_path=None, judge_fn=judge, limit=20)
    assert out["judge_independent"] is True
    assert out["judge_human_agreement"] is not None
    assert len(seen) == 20 and all(isinstance(r, str) for _, r in seen)


@pytest.mark.parametrize("bad", [{"decision": "maybe", "source": "x"}, {"decision": "pass"},
                                 {"decision": "pass", "source": "simulated_heuristic_judge"}])
def test_independent_judge_output_validated(bad):
    case = load_dataset()[0]
    with pytest.raises(ValueError):
        attach_judge(case, "r", _result(case, True), judge_fn=lambda c, r: bad)

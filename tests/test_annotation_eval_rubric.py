import pytest

from annotation_eval.rubric import (
    HumanResponseRubric,
    RubricCriterion,
    RubricRating,
    aggregate_ratings,
    default_chatbot_rubric,
    rater_disagreement,
)
from annotation_eval.schema import LabelProvenance


def _rating(rater, scores, prov=LabelProvenance.HUMAN_INDEPENDENT, response="r1", saw_model=False):
    return RubricRating(
        rubric_id="chatbot_response_v1",
        response_id=response,
        rater_id=rater,
        provenance=prov,
        scores=scores,
        rationale="because",
        saw_model_identity=saw_model,
    )


FULL = {"helpfulness": 4, "factual_accuracy": 5, "safety": 5, "tone": 3}


def test_default_rubric_is_valid():
    rubric = default_chatbot_rubric()
    assert [c.criterion_id for c in rubric.criteria] == ["helpfulness", "factual_accuracy", "safety", "tone"]


def test_anchors_must_cover_scale():
    with pytest.raises(ValueError):
        RubricCriterion(criterion_id="c", description="d", anchors={1: "low", 5: "high"})


def test_duplicate_criteria_rejected():
    c = RubricCriterion(criterion_id="c", description="d", scale_min=1, scale_max=2, anchors={1: "a", 2: "b"})
    with pytest.raises(ValueError):
        HumanResponseRubric(rubric_id="x", version="1", task_type="t", criteria=[c, c])


def test_rating_must_cover_all_criteria_and_range():
    rubric = default_chatbot_rubric()
    with pytest.raises(ValueError):
        _rating("a", {"helpfulness": 4}).validate_against(rubric)
    with pytest.raises(ValueError):
        _rating("a", {**FULL, "tone": 9}).validate_against(rubric)


def test_placeholder_rater_rejected():
    with pytest.raises(ValueError):
        _rating("human.reviewer@example.com", FULL)


def test_aggregate_and_provenance():
    rubric = default_chatbot_rubric()
    out = aggregate_ratings(rubric, [_rating("a", FULL), _rating("b", {**FULL, "tone": 5})])
    assert out["r1"]["criteria"]["tone"]["mean"] == 4.0
    assert out["r1"]["criteria"]["tone"]["n_raters"] == 2
    assert out["r1"]["all_blind_human"] is True


def test_simulated_or_unblinded_ratings_not_blind_human():
    rubric = default_chatbot_rubric()
    out = aggregate_ratings(rubric, [_rating("a", FULL, LabelProvenance.SIMULATED_ANNOTATOR)])
    assert out["r1"]["all_blind_human"] is False
    out = aggregate_ratings(rubric, [_rating("a", FULL, saw_model=True)])
    assert out["r1"]["all_blind_human"] is False


def test_rater_disagreement_flags_large_gaps():
    rubric = default_chatbot_rubric()
    flagged = rater_disagreement(rubric, [_rating("a", FULL), _rating("b", {**FULL, "helpfulness": 1})])
    assert flagged == [{"response_id": "r1", "criterion_id": "helpfulness", "scores": [4, 1]}]

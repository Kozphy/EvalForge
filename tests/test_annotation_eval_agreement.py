import pytest

from annotation_eval.agreement import adjudicate, cohen_kappa, pairwise_agreement, percent_agreement
from annotation_eval.schema import Annotation, LabelProvenance


def test_percent_agreement():
    assert percent_agreement(["a", "b", "a", "a"], ["a", "b", "b", "a"]) == 0.75


def test_cohen_kappa_textbook_example():
    # 2x2 table: yes/yes=20, yes/no=5, no/yes=10, no/no=15 -> p_o=0.7, p_e=0.5, kappa=0.4
    a = ["yes"] * 25 + ["no"] * 25
    b = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
    assert cohen_kappa(a, b) == pytest.approx(0.4)


def test_cohen_kappa_matches_sklearn():
    sklearn_metrics = pytest.importorskip("sklearn.metrics")
    a = ["neg", "neu", "pos", "pos", "neg", "neu", "pos", "neg", "neu", "pos"]
    b = ["neg", "pos", "pos", "pos", "neu", "neu", "pos", "neg", "neg", "pos"]
    assert cohen_kappa(a, b) == pytest.approx(sklearn_metrics.cohen_kappa_score(a, b))


def test_cohen_kappa_perfect_and_chance():
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == pytest.approx(1.0)
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == pytest.approx(0.0)


def test_cohen_kappa_degenerate_raises():
    with pytest.raises(ValueError):
        cohen_kappa(["a", "a"], ["a", "a"])


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        percent_agreement(["a"], ["a", "b"])


def _ann(item, who, label, prov=LabelProvenance.HUMAN_INDEPENDENT):
    return Annotation(item_id=item, annotator_id=who, label=label, provenance=prov)


def test_pairwise_agreement_reports_provenance_and_disagreements():
    anns = [_ann("1", "r1", "x"), _ann("1", "r2", "x"), _ann("2", "r1", "x"), _ann("2", "r2", "y")]
    r = pairwise_agreement(anns, "r1", "r2")
    assert r["n_shared_items"] == 2
    assert r["percent_agreement"] == 0.5
    assert r["is_human_agreement"] is True
    assert r["disagreements"] == [{"item_id": "2", "r1": "x", "r2": "y"}]


def test_simulated_annotators_never_reported_as_human():
    anns = [_ann("1", "s1", "x", LabelProvenance.SIMULATED_ANNOTATOR), _ann("1", "s2", "y", LabelProvenance.SIMULATED_ANNOTATOR)]
    assert pairwise_agreement(anns, "s1", "s2")["is_human_agreement"] is False


def test_adjudication_requires_explicit_decision():
    anns = [_ann("1", "r1", "x"), _ann("1", "r2", "y")]
    with pytest.raises(ValueError, match="unresolved"):
        adjudicate(anns, {"1": "t"})


def test_adjudication_human_inputs_yield_adjudicated_human():
    anns = [_ann("1", "r1", "x"), _ann("1", "r2", "y"), _ann("2", "r1", "z"), _ann("2", "r2", "z")]
    gold = adjudicate(anns, {"1": "t1", "2": "t2"}, {"1": "y"}, adjudicator_id="lead_rater")
    assert [g.gold_label for g in gold] == ["y", "z"]
    assert all(g.provenance == LabelProvenance.ADJUDICATED_HUMAN for g in gold)
    assert gold[0].annotator_id == "lead_rater"


def test_adjudication_keeps_non_human_provenance():
    anns = [_ann("1", "r1", "x"), _ann("1", "s1", "x", LabelProvenance.SIMULATED_ANNOTATOR)]
    gold = adjudicate(anns, {"1": "t"})
    assert gold[0].provenance == LabelProvenance.SIMULATED_ANNOTATOR


def test_adjudicator_id_required_with_decisions():
    with pytest.raises(ValueError):
        adjudicate([_ann("1", "r1", "x")], {"1": "t"}, {"1": "x"})

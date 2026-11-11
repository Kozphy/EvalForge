import pytest

from annotation_eval.metrics import LabelLeakageError, classification_report, confusion_matrix, evaluate_predictions
from annotation_eval.schema import LabeledItem, LabelProvenance, Prediction, PredictorKind


def _item(i, label, prov=LabelProvenance.SYNTHETIC_AUTHOR, annotator=None):
    return LabeledItem(item_id=i, text=f"text {i}", gold_label=label, provenance=prov, annotator_id=annotator)


def _pred(i, label, predictor="rules", kind=PredictorKind.RULE_BASED):
    return Prediction(item_id=i, label=label, predictor=predictor, predictor_kind=kind)


def test_confusion_matrix_counts():
    m = confusion_matrix(["a", "a", "b", "c"], ["a", "b", "b", "a"], ["a", "b", "c"])
    assert m == {"a": {"a": 1, "b": 1, "c": 0}, "b": {"a": 0, "b": 1, "c": 0}, "c": {"a": 1, "b": 0, "c": 0}}


def test_confusion_matrix_rejects_unknown_label():
    with pytest.raises(ValueError):
        confusion_matrix(["a"], ["z"], ["a", "b"])


def test_classification_report_hand_computed():
    gold = ["pos", "pos", "pos", "neg", "neg", "neu"]
    pred = ["pos", "pos", "neg", "neg", "pos", "neu"]
    r = classification_report(gold, pred, ["neg", "neu", "pos"])
    assert r["accuracy"] == round(4 / 6, 4)
    assert r["per_class"]["pos"]["precision"] == round(2 / 3, 4)
    assert r["per_class"]["pos"]["recall"] == round(2 / 3, 4)
    assert r["per_class"]["neg"]["precision"] == 0.5
    assert r["per_class"]["neg"]["recall"] == 0.5
    assert r["per_class"]["neu"]["f1"] == 1.0
    assert r["macro_f1"] == round((2 / 3 + 0.5 + 1.0) / 3, 4)


def test_metrics_are_not_tautological_when_predictions_err():
    items = [_item("1", "x"), _item("2", "y")]
    report = evaluate_predictions(items, [_pred("1", "y"), _pred("2", "x")], ["x", "y"])
    assert report["accuracy"] == 0.0
    assert report["macro_f1"] == 0.0
    assert len(report["errors"]) == 2


def test_self_comparison_is_refused():
    items = [_item("1", "x", annotator="rules")]
    with pytest.raises(LabelLeakageError):
        evaluate_predictions(items, [_pred("1", "x", predictor="rules")], ["x"])


def test_require_human_gold_blocks_synthetic_labels():
    with pytest.raises(LabelLeakageError):
        evaluate_predictions([_item("1", "x")], [_pred("1", "x")], ["x"], require_human_gold=True)


def test_human_gold_is_accepted_and_reported():
    items = [_item("1", "x", LabelProvenance.HUMAN_INDEPENDENT, "rater_7")]
    report = evaluate_predictions(items, [_pred("1", "x")], ["x"], require_human_gold=True)
    assert report["gold_is_independent_human"] is True


def test_report_discloses_synthetic_and_rule_based():
    report = evaluate_predictions([_item("1", "x")], [_pred("1", "x")], ["x"])
    assert report["gold_is_independent_human"] is False
    assert "NOT independent human" in report["interpretation"]
    assert "rule-based baseline" in report["interpretation"]


def test_coverage_mismatch_rejected():
    with pytest.raises(ValueError):
        evaluate_predictions([_item("1", "x"), _item("2", "x")], [_pred("1", "x")], ["x"])


def test_placeholder_email_annotator_rejected():
    with pytest.raises(ValueError):
        _item("1", "x", annotator="human.reviewer@example.com")

import pytest

from research.metrics import (
    binary_metrics,
    bootstrap_confidence_intervals,
    classification_metrics,
    cohen_kappa,
    mcnemar_exact,
    paired_bootstrap,
    paired_bootstrap_difference,
    percentile,
)


def test_binary_metrics_known_confusion_matrix():
    gold = ["fail", "fail", "pass", "pass"]
    pred = ["fail", "pass", "fail", "pass"]

    metrics = binary_metrics(gold, pred)

    assert metrics.tp == 1
    assert metrics.fp == 1
    assert metrics.tn == 1
    assert metrics.fn == 1
    assert metrics.accuracy == 0.5
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f1 == 0.5
    assert metrics.false_positive_rate == 0.5
    assert metrics.false_negative_rate == 0.5


def test_paired_bootstrap_detects_better_system():
    gold = ["fail", "fail", "pass", "pass", "fail", "pass"]
    weaker = ["pass", "fail", "fail", "pass", "pass", "pass"]
    stronger = list(gold)

    result = paired_bootstrap_difference(
        gold,
        weaker,
        stronger,
        iterations=500,
        seed=7,
    )

    assert result["system_b"] > result["system_a"]
    assert result["difference_b_minus_a"] > 0


def test_classification_metrics_hand_computed():
    gold = ["fail", "fail", "fail", "pass", "pass"]
    pred = ["fail", "fail", "pass", "fail", "pass"]
    m = classification_metrics(gold, pred)
    assert (m["tp"], m["fp"], m["tn"], m["fn"]) == (2, 1, 1, 1)
    assert m["accuracy"] == pytest.approx(3 / 5)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(2 / 3)
    # pass class: tp=1, fp=1, fn=1 -> F1 0.5; macro = (2/3 + 1/2) / 2
    assert m["macro_f1"] == pytest.approx((2 / 3 + 0.5) / 2)
    assert m["false_positive_rate"] == pytest.approx(0.5)
    assert m["false_negative_rate"] == pytest.approx(1 / 3)


def test_undefined_metrics_are_none_not_zero():
    m = classification_metrics(["pass", "pass"], ["pass", "pass"])
    assert m["precision"] is None
    assert m["recall"] is None
    assert m["f1"] is None
    assert m["false_negative_rate"] is None
    assert m["false_positive_rate"] == 0.0


def test_class_never_predicted_has_zero_f1_not_undefined():
    m = classification_metrics(["fail", "pass", "pass"], ["fail", "fail", "fail"])
    # pass class: never predicted (precision undefined) but recall is a defined 0 -> F1 0
    assert m["macro_f1"] == pytest.approx((0.5 + 0.0) / 2)


def test_abstentions_count_as_errors_never_false_positives():
    gold = ["fail", "pass", "fail", "pass"]
    pred = [None, None, "fail", "pass"]
    m = classification_metrics(gold, pred)
    assert m["abstained"] == 2
    assert m["n_decided"] == 2
    assert m["accuracy"] == 0.5
    assert m["fp"] == 0
    assert m["fn"] == 1
    assert m["recall"] == 0.5
    assert m["false_positive_rate"] == 0.0


def test_percentile_interpolates():
    assert percentile([0.0, 1.0], 0.5) == 0.5
    assert percentile([1.0, 2.0, 3.0], 0.0) == 1.0
    assert percentile([1.0, 2.0, 3.0], 1.0) == 3.0


def test_bootstrap_is_reproducible_for_a_seed_and_contains_point():
    gold = ["fail"] * 12 + ["pass"] * 8
    pred = ["fail"] * 9 + ["pass"] * 3 + ["pass"] * 6 + ["fail"] * 2
    a = bootstrap_confidence_intervals(gold, pred, iterations=300, seed=11)
    b = bootstrap_confidence_intervals(gold, pred, iterations=300, seed=11)
    c = bootstrap_confidence_intervals(gold, pred, iterations=300, seed=12)
    assert a == b
    assert a != c
    acc = a["accuracy"]
    assert acc["ci_low"] <= acc["point"] <= acc["ci_high"]


def test_paired_bootstrap_identical_systems_has_zero_difference():
    gold = ["fail", "pass", "fail", "pass", "fail"]
    pred = ["fail", "fail", "pass", "pass", "fail"]
    result = paired_bootstrap(gold, pred, pred, iterations=200, seed=1)
    assert result["accuracy"]["difference_b_minus_a"] == 0.0
    assert result["accuracy"]["ci_low"] == result["accuracy"]["ci_high"] == 0.0


def test_mcnemar_exact_known_values():
    gold = ["fail"] * 10
    a = ["pass"] * 10
    b = ["fail"] * 10
    result = mcnemar_exact(gold, a, b)
    assert result["a_wrong_b_correct"] == 10
    assert result["a_correct_b_wrong"] == 0
    assert result["p_value"] == pytest.approx(2 / 2**10)
    assert mcnemar_exact(gold, a, a)["p_value"] == 1.0


def test_cohen_kappa():
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0
    assert cohen_kappa(["a", "a"], ["a", "a"]) is None
    assert cohen_kappa([None], ["a"]) is None

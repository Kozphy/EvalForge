from research.metrics import binary_metrics, paired_bootstrap_difference


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

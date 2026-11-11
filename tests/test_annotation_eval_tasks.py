import json
import shutil

import pytest

from annotation_eval import __main__ as cli
from annotation_eval.baselines import moderation_rule_based, predict, sentiment_rule_based
from annotation_eval.datasets import DATA_DIR, ManifestMismatchError, load_items, load_manifest
from annotation_eval.schema import LabelProvenance, PredictorKind


def test_manifest_declares_synthetic_and_matches_files():
    manifest = load_manifest()
    assert "SYNTHETIC" in manifest["statement"]
    for name, entry in manifest["datasets"].items():
        assert entry["provenance"] in {"synthetic_author", "simulated_annotator"}
        rows = (DATA_DIR / entry["file"]).read_text().strip().splitlines()
        assert len(rows) == entry["rows"]


def test_bundled_items_are_never_marked_human():
    for name in ("sentiment_synthetic_v1", "moderation_synthetic_v1"):
        items = load_items(name)
        assert items and all(i.provenance == LabelProvenance.SYNTHETIC_AUTHOR for i in items)
        assert all("NOT a human annotation" in i.notes for i in items)


def test_tampered_dataset_is_rejected(tmp_path):
    src = DATA_DIR / "sentiment_synthetic_v1.jsonl"
    dst = tmp_path / "tampered.jsonl"
    shutil.copy(src, dst)
    dst.write_text(dst.read_text().replace('"gold_label": "negative"', '"gold_label": "positive"', 1))
    with pytest.raises(ManifestMismatchError):
        load_items("sentiment_synthetic_v1", path=dst)


@pytest.mark.parametrize(
    "text,label",
    [
        ("Great service, very helpful", "positive"),
        ("Terrible and broken", "negative"),
        ("It is not slow", "positive"),
        ("The file is 2 MB", "neutral"),
    ],
)
def test_sentiment_rules(text, label):
    assert sentiment_rule_based(text) == label


@pytest.mark.parametrize(
    "text,label",
    [
        ("You are an idiot", "harassment"),
        ("Click here for free money", "spam"),
        ("Call 555-0100-1234", "personal_data"),
        ("See you tomorrow", "allow"),
    ],
)
def test_moderation_rules(text, label):
    assert moderation_rule_based(text) == label


def test_baseline_predictions_are_labelled_rule_based():
    preds = predict(load_items("sentiment_synthetic_v1"), "sentiment")
    assert {p.predictor_kind for p in preds} == {PredictorKind.RULE_BASED}


@pytest.mark.parametrize("task", ["sentiment", "moderation"])
def test_cli_task_reports_honest_metrics(task, capsys):
    assert cli.main([task]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["n"] == 20
    assert out["gold_is_independent_human"] is False
    assert out["predictor_kinds"] == ["rule_based"]
    assert 0.0 <= out["macro_f1"] <= 1.0
    # The fixtures include cases the rules are expected to miss (sarcasm, implicit PII),
    # so a perfect score would indicate leakage between rules and labels.
    assert out["accuracy"] < 1.0
    assert out["errors"]


def test_cli_agreement_is_simulated(capsys):
    assert cli.main(["agreement"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["is_human_agreement"] is False
    assert out["n_shared_items"] == 12
    assert out["percent_agreement"] == 0.75
    assert out["cohen_kappa"] is not None and out["cohen_kappa"] < 1.0

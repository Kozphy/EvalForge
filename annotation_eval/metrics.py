"""Multi-class classification metrics computed against independent gold labels."""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence

from annotation_eval.schema import HUMAN_PROVENANCES, LabeledItem, Prediction


class LabelLeakageError(ValueError):
    """Raised when gold labels and predictions are not independent."""


def confusion_matrix(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> Dict[str, Dict[str, int]]:
    """Return ``matrix[gold_label][predicted_label] = count``."""
    if len(gold) != len(pred):
        raise ValueError("gold and pred must have the same length")
    unknown = (set(gold) | set(pred)) - set(labels)
    if unknown:
        raise ValueError(f"labels not in label set: {sorted(unknown)}")
    matrix = {g: {p: 0 for p in labels} for g in labels}
    for g, p in zip(gold, pred):
        matrix[g][p] += 1
    return matrix


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def classification_report(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> dict:
    """Per-class precision/recall/F1/support plus accuracy and macro/weighted F1."""
    matrix = confusion_matrix(gold, pred, labels)
    per_class: Dict[str, dict] = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[g][label] for g in labels if g != label)
        fn = sum(matrix[label][p] for p in labels if p != label)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp + fn,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
    total = len(gold)
    correct = sum(1 for g, p in zip(gold, pred) if g == p)
    supports = [per_class[label]["support"] for label in labels]
    macro_f1 = _safe_div(sum(per_class[label]["f1"] for label in labels), len(labels))
    weighted_f1 = _safe_div(sum(per_class[label]["f1"] * s for label, s in zip(labels, supports)), total)
    return {
        "n": total,
        "accuracy": round(_safe_div(correct, total), 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "per_class": per_class,
        "confusion_matrix": matrix,
        "labels": list(labels),
    }


def evaluate_predictions(
    items: Iterable[LabeledItem],
    predictions: Iterable[Prediction],
    labels: Sequence[str],
    *,
    require_human_gold: bool = False,
) -> dict:
    """Score predictions against gold labels, refusing self-comparison.

    * Every item must have exactly one prediction and vice versa.
    * A predictor may not grade itself: if any gold label's annotator id equals
      the predictor name, ``LabelLeakageError`` is raised.
    * The output always states the gold-label provenance mix and predictor kind
      so a rule-based baseline scored on synthetic labels cannot be reported as
      a validated model.
    """
    items = list(items)
    predictions = list(predictions)
    by_id = {p.item_id: p for p in predictions}
    if len(by_id) != len(predictions):
        raise ValueError("duplicate prediction item_id")
    gold_ids = [i.item_id for i in items]
    if len(set(gold_ids)) != len(gold_ids):
        raise ValueError("duplicate gold item_id")
    if set(gold_ids) != set(by_id):
        raise ValueError("predictions and gold items cover different item_ids")
    predictors = {p.predictor for p in predictions}
    annotators = {i.annotator_id for i in items if i.annotator_id}
    if predictors & annotators:
        raise LabelLeakageError(f"predictor also authored gold labels: {sorted(predictors & annotators)}")
    if require_human_gold and not all(i.provenance in HUMAN_PROVENANCES for i in items):
        raise LabelLeakageError("require_human_gold=True but some gold labels are not independent human labels")

    gold = [i.gold_label for i in items]
    pred = [by_id[i.item_id].label for i in items]
    report = classification_report(gold, pred, labels)
    provenance_counts = Counter(i.provenance.value for i in items)
    report["gold_provenance"] = dict(sorted(provenance_counts.items()))
    report["gold_is_independent_human"] = all(i.provenance in HUMAN_PROVENANCES for i in items)
    report["predictor_kinds"] = sorted({p.predictor_kind.value for p in predictions})
    report["predictors"] = sorted(predictors)
    report["errors"] = [
        {"item_id": i.item_id, "gold": i.gold_label, "pred": by_id[i.item_id].label}
        for i in items
        if i.gold_label != by_id[i.item_id].label
    ]
    report["interpretation"] = interpretation_note(report)
    return report


def interpretation_note(report: dict) -> str:
    """Plain-language caveat that must accompany any reported number."""
    parts: List[str] = []
    if not report.get("gold_is_independent_human"):
        parts.append("gold labels are NOT independent human annotations (" + ", ".join(report.get("gold_provenance", {})) + ")")
    kinds: Optional[List[str]] = report.get("predictor_kinds")
    if kinds == ["rule_based"]:
        parts.append("predictions come from a rule-based baseline, not a trained ML model")
    parts.append(f"n={report.get('n')} items; not a benchmark or production evidence")
    return "; ".join(parts)

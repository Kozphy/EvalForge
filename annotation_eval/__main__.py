"""CLI: ``python -m annotation_eval {sentiment,moderation,agreement}``.

Runs fully offline. Output always includes provenance and an interpretation
note so rule-based scores on synthetic fixtures are not mistaken for
validated model performance.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from annotation_eval.agreement import pairwise_agreement
from annotation_eval.baselines import MODERATION_LABELS, SENTIMENT_LABELS, predict
from annotation_eval.datasets import load_annotations, load_items
from annotation_eval.metrics import evaluate_predictions


def run(task: str) -> dict:
    if task == "sentiment":
        items = load_items("sentiment_synthetic_v1")
        return {"task": task, "dataset": "sentiment_synthetic_v1", **evaluate_predictions(items, predict(items, task), SENTIMENT_LABELS)}
    if task == "moderation":
        items = load_items("moderation_synthetic_v1")
        return {"task": task, "dataset": "moderation_synthetic_v1", **evaluate_predictions(items, predict(items, task), MODERATION_LABELS)}
    if task == "agreement":
        anns = load_annotations("agreement_simulated_v1")
        result = pairwise_agreement(anns, "sim_annotator_a", "sim_annotator_b")
        result["interpretation"] = "scripted simulated annotators; demonstrates the computation only, not human inter-annotator agreement"
        return {"task": task, "dataset": "agreement_simulated_v1", **result}
    raise ValueError(f"unknown task: {task}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m annotation_eval", description=__doc__)
    parser.add_argument("task", choices=["sentiment", "moderation", "agreement"])
    args = parser.parse_args(argv)
    json.dump(run(args.task), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Analyze EvalForge experiment predictions.

Input format: CSV with columns
case_id,gold_label,<system columns...>

Example:
case_id,gold_label,rule_baseline,evalforge_hybrid
c001,fail,pass,fail
c002,pass,pass,pass
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from research.metrics import binary_metrics, paired_bootstrap_difference


def load_predictions(path: Path, systems: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        raise ValueError("prediction CSV is empty")

    required = {"case_id", "gold_label", *systems}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    gold = [row["gold_label"].strip() for row in rows]
    predictions = {system: [row[system].strip() for row in rows] for system in systems}
    return gold, predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze paired EvalForge benchmark predictions")
    parser.add_argument("predictions", type=Path, help="CSV containing gold labels and system predictions")
    parser.add_argument("--systems", nargs="+", required=True, help="prediction columns to evaluate")
    parser.add_argument("--compare", nargs=2, metavar=("SYSTEM_A", "SYSTEM_B"))
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("research/results/metrics.json"))
    args = parser.parse_args()

    gold, predictions = load_predictions(args.predictions, args.systems)

    report: dict[str, object] = {
        "n_cases": len(gold),
        "systems": {
            system: binary_metrics(gold, pred).to_dict()
            for system, pred in predictions.items()
        },
    }

    if args.compare:
        a, b = args.compare
        if a not in predictions or b not in predictions:
            raise ValueError("--compare systems must also be listed in --systems")
        report["paired_bootstrap"] = paired_bootstrap_difference(
            gold,
            predictions[a],
            predictions[b],
            iterations=args.iterations,
            seed=args.seed,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

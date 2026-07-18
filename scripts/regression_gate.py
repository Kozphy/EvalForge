#!/usr/bin/env python3
"""Fail CI when an exported EvalForge run breaches configured thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.regression import RegressionThresholds, evaluate_run_gate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_json", type=Path, help="JSON export from /api/runs/{id}/export")
    parser.add_argument("--min-accuracy", type=float)
    parser.add_argument("--max-review-rate", type=float)
    parser.add_argument("--max-block-rate", type=float)
    parser.add_argument("--min-groundedness", type=float)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = json.loads(args.run_json.read_text(encoding="utf-8"))
    thresholds = RegressionThresholds(
        min_accuracy=args.min_accuracy,
        max_review_rate=args.max_review_rate,
        max_block_rate=args.max_block_rate,
        min_groundedness=args.min_groundedness,
    )
    result = evaluate_run_gate(payload, thresholds)
    print(result.model_dump_json(indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

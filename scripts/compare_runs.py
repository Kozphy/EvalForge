from __future__ import annotations

import argparse
import json

from app.comparison_service import RegressionPolicy, compare_runs
from app.db import init_db


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare a candidate EvalForge run against a baseline run."
    )
    parser.add_argument("baseline_run_id", type=int)
    parser.add_argument("candidate_run_id", type=int)
    parser.add_argument("--max-accuracy-drop", type=float, default=0.0)
    parser.add_argument("--max-new-major-regressions", type=int, default=0)
    parser.add_argument(
        "--major-label",
        action="append",
        dest="major_labels",
        help="Label treated as a major regression. Repeat for multiple labels.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with status 1 when the comparison gate fails.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    init_db()
    policy = RegressionPolicy(
        max_accuracy_drop=args.max_accuracy_drop,
        max_new_major_regressions=args.max_new_major_regressions,
        major_labels=tuple(args.major_labels or ("major", "critical")),
    )
    comparison = compare_runs(
        args.baseline_run_id,
        args.candidate_run_id,
        policy,
    )
    print(json.dumps(comparison, indent=2, ensure_ascii=False))
    if args.fail_on_regression and comparison["decision"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

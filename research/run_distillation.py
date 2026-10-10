"""CLI policy gate for teacher-versus-student response distillation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .distillation import DistillationPolicy, evaluate_distillation, load_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Paired teacher/student JSONL")
    parser.add_argument("--output", type=Path, help="Write the JSON report")
    parser.add_argument("--min-quality-retention", type=float, default=0.90)
    parser.add_argument("--max-quality-drop", type=float, default=0.10)
    parser.add_argument("--min-cost-reduction", type=float, default=0.50)
    parser.add_argument("--min-latency-reduction", type=float, default=0.20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    policy = DistillationPolicy(
        min_quality_retention=args.min_quality_retention,
        max_student_quality_drop=args.max_quality_drop,
        min_cost_reduction=args.min_cost_reduction,
        min_latency_reduction=args.min_latency_reduction,
    )
    report = evaluate_distillation(load_jsonl(args.dataset), policy)
    rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

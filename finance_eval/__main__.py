"""CLI for finance evaluation vertical."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finance_eval.generate_dataset import write_dataset
from finance_eval.live import LiveModelClient, LiveRunBudget
from finance_eval.report import write_report
from finance_eval.runner import DEFAULT_BASELINE, DEFAULT_DATASET, DEFAULT_LIVE_SUMMARY, run_evaluation
from finance_eval.taxonomy import taxonomy_catalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EvalForge finance evaluation vertical")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("generate-dataset", help="Regenerate frozen golden set + manifest")
    sub.add_parser("taxonomy", help="Print failure taxonomy catalog")

    run_p = sub.add_parser("run", help="Run evaluation pipeline (offline or live)")
    run_p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run_p.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    run_p.add_argument("--write-baseline", action="store_true")
    run_p.add_argument("--evidence-dir", type=Path, default=None)
    run_p.add_argument("--model", default="offline-candidate-fixture")
    run_p.add_argument("--model-version", default="v1")
    run_p.add_argument("--mode", choices=["candidate", "gold", "live"], default="candidate")
    run_p.add_argument("--provider", choices=["openai", "anthropic", "mock"], default="openai")
    run_p.add_argument("--live-model", default=None, help="Provider model id (e.g. gpt-4o-mini)")
    run_p.add_argument("--limit", type=int, default=None, help="Max cases (recommended for live)")
    run_p.add_argument("--max-cost-usd", type=float, default=1.0)
    run_p.add_argument("--max-retries", type=int, default=2)
    run_p.add_argument("--timeout-s", type=float, default=60.0)
    run_p.add_argument("--live-summary", type=Path, default=DEFAULT_LIVE_SUMMARY)

    rep = sub.add_parser("report", help="Run evaluation and write markdown report")
    rep.add_argument("--out", type=Path, default=Path("docs/reports/finance-evaluation-report.md"))
    rep.add_argument("--write-baseline", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "generate-dataset":
        print(json.dumps(write_dataset(), indent=2))
        return 0
    if args.cmd == "taxonomy":
        print(json.dumps(taxonomy_catalog(), indent=2))
        return 0
    if args.cmd == "run":
        kwargs: dict = {
            "dataset_path": args.dataset,
            "baseline_path": args.baseline,
            "write_baseline": args.write_baseline,
            "model": args.model,
            "model_version": args.model_version,
            "mode": args.mode if args.mode != "live" else "candidate",
            "limit": args.limit,
        }
        if args.evidence_dir:
            kwargs["evidence_dir"] = args.evidence_dir
        if args.mode == "live":
            live_model = args.live_model or (
                "gpt-4o-mini" if args.provider == "openai" else "claude-3-5-haiku-latest"
            )
            if args.provider == "mock":
                live_model = args.live_model or "mock-model"
            client = LiveModelClient(
                provider=args.provider,
                model=live_model,
                budget=LiveRunBudget(
                    max_cost_usd=args.max_cost_usd,
                    max_retries=args.max_retries,
                    timeout_s=args.timeout_s,
                    limit=args.limit,
                ),
            )
            kwargs["live_client"] = client
            kwargs["live_summary_path"] = args.live_summary
            kwargs.pop("mode", None)
        result = run_evaluation(**kwargs)
        print(
            json.dumps(
                {
                    "n_cases": result["n_cases"],
                    "metrics": result["metrics"],
                    "policy": result["policy"],
                    "judge_human_agreement": result["judge_human_agreement"],
                    "run_id": result["manifest"]["run_id"],
                    "live_budget": result.get("live_budget"),
                    "stopped_reason": result.get("stopped_reason"),
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "report":
        run_evaluation(mode="gold", write_baseline=True)
        result = run_evaluation(mode="candidate", write_baseline=False)
        path = write_report(result, args.out)
        print(f"Wrote {path}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

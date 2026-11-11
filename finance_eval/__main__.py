"""CLI for finance evaluation vertical."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finance_eval.generate_dataset import write_dataset
from finance_eval.live import LiveModelClient, LiveRunBudget
from finance_eval.report import write_report
from finance_eval.runner import (
    DEFAULT_BASELINE,
    DEFAULT_DATASET,
    DEFAULT_MOCK_LIVE_SUMMARY,
    DatasetIntegrityError,
    run_evaluation,
)
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
    run_p.add_argument("--provider", choices=["openai", "anthropic", "mock", "ollama", "replay"], default=None,
                       help="Required with --mode live. openai/anthropic are paid and also need --allow-paid")
    run_p.add_argument("--allow-paid", action="store_true", help="Opt in to paid providers (also needs EVALFORGE_ALLOW_PAID=1)")
    run_p.add_argument("--ollama-url", default="http://localhost:11434")
    run_p.add_argument("--replay", type=Path, default=None, help="Run record JSONL to replay offline")
    run_p.add_argument("--record", type=Path, default=None, help="Write a run record JSONL (refuses to overwrite)")
    run_p.add_argument("--model-digest", default=None, help="Model digest, e.g. from `ollama show --modelfile` / `ollama list`")
    run_p.add_argument("--live-model", default=None, help="Provider model id (e.g. gpt-4o-mini)")
    run_p.add_argument("--limit", type=int, default=None, help="Max cases (recommended for live)")
    run_p.add_argument("--max-cost-usd", type=float, default=1.0)
    run_p.add_argument("--max-retries", type=int, default=2)
    run_p.add_argument("--timeout-s", type=float, default=60.0)
    run_p.add_argument(
        "--live-summary",
        type=Path,
        default=None,
        help="Redacted summary path. Default: gitignored finance_eval/output/live_run_summary.<provider>.json",
    )

    rep = sub.add_parser("report", help="Run evaluation and write markdown report")
    rep.add_argument("--out", type=Path, default=Path("docs/reports/finance-evaluation-report.md"))
    rep.add_argument("--write-baseline", action="store_true")

    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except DatasetIntegrityError as exc:
        # Fail closed: no responses were requested and no evidence or baseline was written.
        print(f"error: dataset integrity check failed: {exc}", file=sys.stderr)
        return 2


def _usage_error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _dispatch(args: argparse.Namespace) -> int:

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
            if args.provider is None:
                _usage_error("--mode live requires an explicit --provider")
            live_model = args.live_model or (
                "gpt-4o-mini" if args.provider == "openai" else "claude-3-5-haiku-latest"
            )
            if args.provider == "mock":
                live_model = args.live_model or "mock-model"
            if args.provider in {"ollama", "replay"}:
                if not args.live_model:
                    _usage_error(f"--provider {args.provider} requires --live-model")
                live_model = args.live_model
            if args.provider == "replay" and args.replay is None:
                _usage_error("--provider replay requires --replay PATH")
            recorder = None
            if args.provider in {"ollama", "openai", "anthropic"}:
                if args.record is None:
                    _usage_error(f"--provider {args.provider} requires --record PATH so outputs are auditable")
                from urllib.parse import urlparse

                from finance_eval import DATASET_VERSION, PROMPT_VERSION
                from finance_eval.evidence import sha256_file
                from finance_eval.live import SYSTEM_PROMPT
                from finance_eval.recording import RunHeader, RunRecorder, sha256_text

                endpoints = {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}
                host = endpoints.get(args.provider) or (urlparse(args.ollama_url).hostname or "")
                recorder = RunRecorder(args.record, RunHeader(
                    run_id=args.record.stem,
                    started_at_utc=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                    provider=args.provider, model=live_model, model_digest=args.model_digest,
                    endpoint_host=host, is_local=args.provider == "ollama", paid=args.provider in endpoints,
                    temperature=0.0, seed=0 if args.provider == "ollama" else None, max_output_tokens=1024,
                    system_prompt_sha256=sha256_text(SYSTEM_PROMPT), prompt_version=PROMPT_VERSION,
                    dataset_version=DATASET_VERSION, dataset_sha256=sha256_file(args.dataset),
                    max_cost_usd=args.max_cost_usd, limit=args.limit,
                ))
            client = LiveModelClient(
                provider=args.provider,
                model=live_model,
                budget=LiveRunBudget(
                    max_cost_usd=args.max_cost_usd,
                    max_retries=args.max_retries,
                    timeout_s=args.timeout_s,
                    limit=args.limit,
                ),
                allow_paid=args.allow_paid,
                base_url=args.ollama_url,
                replay_path=args.replay,
                recorder=recorder,
            )
            kwargs["live_client"] = client
            if args.live_summary is not None:
                kwargs["live_summary_path"] = args.live_summary
            else:
                # Never default to the committed example file.
                kwargs["live_summary_path"] = (
                    DEFAULT_MOCK_LIVE_SUMMARY
                    if args.provider == "mock"
                    else DEFAULT_MOCK_LIVE_SUMMARY.with_name(f"live_run_summary.{args.provider}.json")
                )
            kwargs.pop("mode", None)
        result = run_evaluation(**kwargs)
        if args.mode == "live" and kwargs["live_client"].recorder is not None:
            result["run_record_sha256"] = kwargs["live_client"].recorder.close()
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
                    "run_record_sha256": result.get("run_record_sha256"),
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

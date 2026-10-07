"""Run the RQ1/RQ2 experiment.

    python -m research.run --config research/config/smoke.yaml     # offline, no paid API
    python -m research.run --config research/config/default.yaml   # LLM judge (needs OPENAI_API_KEY)

Writes ``research/results/<experiment_id>/`` and refuses to overwrite an existing
directory. Artifact hashes are recorded in ``manifest.json``; use
``python -m research.run --verify <dir>`` to check a results directory is unmodified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import yaml

from app.controls import ControlPolicy
from finance_eval.live import CostCapExceeded, LiveRunBudget
from research import analysis
from research.dataset import SPLITS, load_corpus, load_split, verify_integrity
from research.judge import (
    JUDGE_PROMPT_VERSION,
    JUDGE_SYSTEM_PROMPT,
    HeuristicJudge,
    LLMJudge,
    ReplayJudge,
)
from research.systems import SYSTEMS, RetrievalConfig, evaluate_case

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parent / "results"
ARTIFACTS = (
    "predictions.jsonl",
    "evidence.jsonl",
    "judge_raw.jsonl",
    "disagreements.jsonl",
    "errors.jsonl",
    "metrics.json",
    "confidence_intervals.json",
    "report.md",
)
_PACKAGES = ("pydantic", "scikit-learn", "scipy", "numpy", "httpx", "PyYAML", "openai")


class ResultsExistError(FileExistsError):
    pass


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_bytes("".join(json.dumps(r, sort_keys=True, ensure_ascii=True) + "\n" for r in rows).encode("utf-8"))


def _write_json(path: Path, obj: dict) -> None:
    path.write_bytes((json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8"))


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=15
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _git_info() -> dict:
    status = _git("status", "--porcelain")
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": None if status is None else bool(status),
    }


def _runtime() -> dict:
    packages = {}
    for name in _PACKAGES:
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": sys.version.split()[0], "platform": platform.platform(), "packages": packages}


def load_config(path: Path) -> dict:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for key in ("experiment", "judge", "retrieval", "routing", "systems", "bootstrap"):
        if key not in config:
            raise ValueError(f"config missing required section: {key}")
    unknown = [s for s in config["systems"] if s not in SYSTEMS]
    if unknown:
        raise ValueError(f"unknown systems in config: {unknown}")
    return config


def build_judge(judge_cfg: dict, *, transport=None):
    backend = judge_cfg["backend"]
    if backend == "heuristic_standin":
        return HeuristicJudge(), None
    if backend == "replay":
        return ReplayJudge(REPO_ROOT / judge_cfg["replay_path"]), None
    if backend == "llm":
        budget = LiveRunBudget(
            max_cost_usd=float(judge_cfg["max_cost_usd"]),
            max_retries=int(judge_cfg["max_retries"]),
            timeout_s=float(judge_cfg["timeout_s"]),
        )
        judge = LLMJudge(
            provider=judge_cfg["provider"],
            model=judge_cfg["model"],
            temperature=float(judge_cfg["temperature"]),
            max_tokens=int(judge_cfg["max_tokens"]),
            budget=budget,
            transport=transport,
        )
        return judge, budget
    raise ValueError(f"unknown judge backend: {backend}")


def run_experiment(
    config_path: Path,
    *,
    experiment_id: str | None = None,
    results_root: Path | None = None,
    allow_holdout: bool = False,
    splits: list[str] | None = None,
    transport=None,
    command: str | None = None,
) -> Path:
    config = load_config(config_path)
    exp = config["experiment"]
    selected_splits = splits or exp["splits"]
    for split in selected_splits:
        if split not in SPLITS:
            raise ValueError(f"unknown split {split}")
    if "holdout" in selected_splits and not allow_holdout:
        raise PermissionError("holdout split requested without --allow-holdout")

    dataset_manifest = verify_integrity()
    cases = [c for split in selected_splits for c in load_split(split, allow_holdout=allow_holdout)]
    corpus = load_corpus()

    created = datetime.now(timezone.utc)
    experiment_id = experiment_id or f"{exp['name']}-{created.strftime('%Y%m%dT%H%M%SZ')}"
    out_dir = Path(results_root or DEFAULT_RESULTS_ROOT) / experiment_id
    if out_dir.exists():
        raise ResultsExistError(f"{out_dir} already exists; results are immutable. Use a new experiment id.")

    judge_cfg = config["judge"]
    judge, budget = build_judge(judge_cfg, transport=transport)
    retrieval = RetrievalConfig(**config["retrieval"])
    policy = ControlPolicy(**config["routing"])
    seed = int(exp["seed"])
    boot = config["bootstrap"]

    predictions: list[dict] = []
    evidence_rows: list[dict] = []
    judge_raw: dict[str, dict] = {}
    errors: list[dict] = []
    status = "complete"
    stopped_reason = None
    calls_made = cache_hits = 0
    model_versions: set[str] = set()

    try:
        for system in config["systems"]:
            spec = SYSTEMS[system]
            for case in cases:
                try:
                    pred, call, request, evidence = evaluate_case(
                        case, spec, corpus=corpus, judge=judge, retrieval=retrieval, policy=policy
                    )
                except CostCapExceeded:
                    raise
                except Exception as exc:  # noqa: BLE001 - recorded; the case becomes an abstention
                    errors.append({"system": system, "case_id": case.case_id, "stage": "evaluate_case",
                                   "error": f"{type(exc).__name__}: {exc}"})
                    predictions.append(_failed_prediction(case, system))
                    continue
                predictions.append(pred)
                if spec.use_retrieval:
                    evidence_rows.append({
                        "system": system,
                        "case_id": case.case_id,
                        "evidence": evidence,
                        "gold_evidence_ids": list(case.gold_evidence_ids),
                        "gold_evidence_retrieved": set(case.gold_evidence_ids) <= {e["doc_id"] for e in evidence},
                    })
                if call is not None and request is not None:
                    if call.cache_hit:
                        cache_hits += 1
                    else:
                        calls_made += 1
                    if call.model_version:
                        model_versions.add(call.model_version)
                    record = judge_raw.setdefault(call.request_sha256, {**call.record(request), "used_by": []})
                    record["used_by"].append({"system": system, "case_id": case.case_id})
                    if call.parse_error or call.call_error:
                        errors.append({"system": system, "case_id": case.case_id, "stage": "judge",
                                       "parse_error": call.parse_error, "call_error": call.call_error,
                                       "request_sha256": call.request_sha256})
    except CostCapExceeded as exc:
        status = "aborted_cost_cap"
        stopped_reason = str(exc)
        errors.append({"stage": "budget", "error": stopped_reason})

    return _write_results(
        out_dir=out_dir,
        experiment_id=experiment_id,
        created=created,
        config=config,
        config_path=Path(config_path),
        dataset_manifest=dataset_manifest,
        selected_splits=selected_splits,
        cases=cases,
        corpus=corpus,
        retrieval=retrieval,
        policy=policy,
        judge=judge,
        judge_cfg=judge_cfg,
        budget=budget,
        predictions=predictions,
        evidence_rows=evidence_rows,
        judge_raw=judge_raw,
        errors=errors,
        status=status,
        stopped_reason=stopped_reason,
        calls_made=calls_made,
        cache_hits=cache_hits,
        model_versions=model_versions,
        seed=seed,
        boot=boot,
        allow_holdout=allow_holdout,
        command=command,
    )


def _failed_prediction(case, system: str) -> dict:
    return {
        "case_id": case.case_id, "system": system, "gold_label": case.gold_label,
        "gold_category": case.failure_category, "predicted_label": None, "predicted_category": None,
        "correct": False, "decision_reasons": ["evaluation_error"], "routed_to_human": False,
        "route_reasons": [], "judge_label": None, "judge_confidence": None, "judge_category": None,
        "judge_reason": None, "judge_request_sha256": None, "judge_cache_hit": None,
        "judge_parse_error": None, "judge_call_error": None, "failed_rules": [], "invalid_citations": [],
        "evidence_ids": [], "gold_evidence_ids": list(case.gold_evidence_ids), "controls_action": None,
        "controls_failed": [], "latency_ms": None, "judge_latency_ms": None, "cost_usd": None,
        "ambiguous": case.ambiguous,
    }


def _write_results(**kw) -> Path:
    out_dir: Path = kw["out_dir"]
    predictions: list[dict] = kw["predictions"]
    cases = kw["cases"]
    corpus = kw["corpus"]
    retrieval: RetrievalConfig = kw["retrieval"]
    evidence_rows: list[dict] = kw["evidence_rows"]
    evidence_index = {(row["system"], row["case_id"]): row for row in evidence_rows}

    judge = kw["judge"]
    judge_is_llm = bool(getattr(judge, "is_llm", False))
    by_system = analysis.group_by_system(predictions)
    complete = kw["status"] == "complete"
    boot = kw["boot"]
    metrics = (
        {s: analysis.system_metrics(s, preds, judge_is_llm) for s, preds in by_system.items()} if complete else {}
    )
    cis = analysis.confidence_intervals(by_system, int(boot["iterations"]), int(boot["seed"])) if complete else {}
    comps = analysis.comparisons(by_system, int(boot["iterations"]), int(boot["seed"])) if complete else {}
    disagreement_rows = analysis.disagreements(predictions, evidence_index)

    judge_cfg = kw["judge_cfg"]
    budget = kw["budget"]
    dataset_manifest = kw["dataset_manifest"]
    evidence_label = (
        "local benchmark on synthetic, single-author-labelled data (external validation E0); "
        + ("LLM judge" if judge_is_llm else "offline heuristic stand-in judge (NOT an LLM)")
    )
    manifest = {
        "experiment_id": kw["experiment_id"],
        "status": kw["status"],
        "stopped_reason": kw["stopped_reason"],
        "created_utc": kw["created"].isoformat(),
        "command": kw["command"] or "python -m research.run",
        "config_path": kw["config_path"].as_posix(),
        "config": kw["config"],
        "config_sha256": hashlib.sha256(kw["config_path"].read_bytes()).hexdigest(),
        "git": _git_info(),
        "dataset": {
            "name": dataset_manifest["dataset_name"],
            "version": dataset_manifest["version"],
            "dataset_sha256": dataset_manifest["dataset_sha256"],
            "splits": kw["selected_splits"],
            "holdout_used": "holdout" in kw["selected_splits"],
            "n_cases": len(cases),
            "case_ids": [c.case_id for c in cases],
        },
        "judge": {
            "backend": judge.backend,
            "is_llm": judge_is_llm,
            "provider": judge_cfg.get("provider"),
            "model": judge_cfg.get("model") if judge_cfg["backend"] == "llm" else getattr(judge, "source", judge.backend),
            "model_versions_reported_by_provider": sorted(kw["model_versions"]),
            "temperature": judge_cfg.get("temperature"),
            "max_tokens": judge_cfg.get("max_tokens"),
            "prompt_version": JUDGE_PROMPT_VERSION,
            "system_prompt_sha256": hashlib.sha256(JUDGE_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "api_key_env": judge_cfg.get("api_key_env"),
            "cost_cap_usd": judge_cfg.get("max_cost_usd"),
            "estimated_spend_usd": round(budget.spent_usd, 6) if budget is not None else 0.0,
            "calls_made": kw["calls_made"],
            "cache_hits": kw["cache_hits"],
        },
        "retrieval": {**retrieval.__dict__, "corpus_documents": len(corpus)},
        "routing_policy": kw["policy"].model_dump(),
        "seed": kw["seed"],
        "bootstrap": boot,
        "systems": list(kw["config"]["systems"]),
        "runtime": _runtime(),
        "evidence_label": evidence_label,
        "errors_recorded": len(kw["errors"]),
    }

    out_dir.mkdir(parents=True, exist_ok=False)
    _write_jsonl(out_dir / "predictions.jsonl", predictions)
    _write_jsonl(out_dir / "evidence.jsonl", evidence_rows)
    _write_jsonl(out_dir / "judge_raw.jsonl", list(kw["judge_raw"].values()))
    _write_jsonl(out_dir / "disagreements.jsonl", disagreement_rows)
    _write_jsonl(out_dir / "errors.jsonl", kw["errors"])
    _write_json(out_dir / "metrics.json", {"experiment_id": kw["experiment_id"], "status": kw["status"],
                                           "systems": metrics, "comparisons": comps})
    _write_json(out_dir / "confidence_intervals.json", {"method": "percentile bootstrap over cases",
                                                         "iterations": boot["iterations"], "seed": boot["seed"],
                                                         "systems": cis})
    report = (
        analysis.render_report({**manifest}, metrics, cis, comps, disagreement_rows)
        if complete
        else f"# Experiment `{kw['experiment_id']}` incomplete\n\nStatus: {kw['status']} - {kw['stopped_reason']}\n"
    )
    (out_dir / "report.md").write_bytes(report.encode("utf-8"))
    manifest["artifacts"] = {name: _sha256_file(out_dir / name) for name in ARTIFACTS}
    _write_json(out_dir / "manifest.json", manifest)
    return out_dir


def verify_results(out_dir: Path) -> list[str]:
    """Return a list of problems; empty means every artifact matches the manifest."""
    manifest = json.loads((Path(out_dir) / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    for name, expected in manifest["artifacts"].items():
        path = Path(out_dir) / name
        if not path.exists():
            problems.append(f"missing {name}")
        elif _sha256_file(path) != expected:
            problems.append(f"modified {name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.run")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--experiment-id")
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--splits", nargs="+", help="override config splits (e.g. dev while debugging)")
    parser.add_argument("--allow-holdout", action="store_true",
                        help="required to touch the holdout split; use once, for the final run")
    parser.add_argument("--verify", type=Path, help="verify an existing results directory and exit")
    args = parser.parse_args(argv)

    if args.verify:
        problems = verify_results(args.verify)
        print("OK: all artifacts match manifest" if not problems else "\n".join(problems))
        return 0 if not problems else 1
    if not args.config:
        parser.error("--config is required")
    command = "python -m research.run " + " ".join(argv if argv is not None else sys.argv[1:])
    out_dir = run_experiment(
        args.config,
        experiment_id=args.experiment_id,
        results_root=args.results_root,
        allow_holdout=args.allow_holdout,
        splits=args.splits,
        command=command,
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"{manifest['status']}: {out_dir}")
    try:
        print(f"report: {out_dir.relative_to(REPO_ROOT) / 'report.md'}")
    except ValueError:
        print(f"report: {out_dir / 'report.md'}")
    return 0 if manifest["status"] == "complete" else 2


if __name__ == "__main__":
    sys.exit(main())

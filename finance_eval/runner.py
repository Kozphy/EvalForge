"""Finance evaluation runner: dataset → grade → judge → review → policy → evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from finance_eval import DATASET_VERSION, PROMPT_VERSION
from finance_eval.evidence import sha256_file, write_evidence_bundle
from finance_eval.graders import grade_case
from finance_eval.human_review import agreement_rate, load_reviews, seed_human_reviews
from finance_eval.judge import attach_judge
from finance_eval.live import (
    CostCapExceeded,
    LiveModelClient,
    LiveRunBudget,
    ModelCallResult,
    write_redacted_live_summary,
)
from finance_eval.metrics import aggregate_metrics, metrics_to_dict
from finance_eval.policy import compare_to_baseline, evaluate_policy
from finance_eval.schema import CaseResult, FinanceCase
from finance_eval.taxonomy import FinanceFailureCode as F

ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "dataset" / "finance_accounting_v1.jsonl"
DEFAULT_MANIFEST = ROOT / "dataset" / "MANIFEST.json"
DEFAULT_BASELINE = ROOT / "baselines" / "baseline_metrics.json"
DEFAULT_EVIDENCE = ROOT / "output" / "evidence"
DEFAULT_REVIEWS = ROOT / "output" / "human_reviews.jsonl"
DEFAULT_LIVE_SUMMARY = ROOT / "baselines" / "live_run_summary.example.json"

ResponseFn = Callable[[FinanceCase], str | ModelCallResult]


class DatasetIntegrityError(RuntimeError):
    """Raised when the dataset on disk does not match its pinned MANIFEST hash."""


def resolve_dataset_manifest(dataset_path: Path, manifest_path: Path | None = None) -> Path:
    """Locate the integrity manifest for a dataset (fail closed if none)."""
    dataset_path = dataset_path.resolve()
    if manifest_path is not None:
        return manifest_path.resolve()
    sibling = dataset_path.parent / "MANIFEST.json"
    if sibling.is_file():
        return sibling.resolve()
    if dataset_path == DEFAULT_DATASET.resolve() and DEFAULT_MANIFEST.is_file():
        return DEFAULT_MANIFEST.resolve()
    raise DatasetIntegrityError(
        f"No MANIFEST.json found for dataset {dataset_path}; refuse to grade unpinned data"
    )


def verify_dataset_integrity(
    dataset_path: Path,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Fail closed: refuse to grade unless file sha256 matches the pinned MANIFEST.

    Returns a small audit record suitable for the evidence manifest.
    """
    dataset_path = dataset_path.resolve()
    if not dataset_path.is_file():
        raise DatasetIntegrityError(f"Dataset file not found: {dataset_path}")

    pinned_path = resolve_dataset_manifest(dataset_path, manifest_path)
    if not pinned_path.is_file():
        raise DatasetIntegrityError(f"MANIFEST not found: {pinned_path}")

    try:
        pinned = json.loads(pinned_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetIntegrityError(f"MANIFEST is not valid JSON: {pinned_path}") from exc

    expected = pinned.get("sha256")
    if not isinstance(expected, str) or not expected.strip():
        raise DatasetIntegrityError(f"MANIFEST missing sha256: {pinned_path}")

    observed = sha256_file(dataset_path)
    if observed != expected:
        raise DatasetIntegrityError(
            "Dataset sha256 does not match MANIFEST "
            f"(expected={expected}, observed={observed}, dataset={dataset_path}, "
            f"manifest={pinned_path})"
        )

    pinned_version = pinned.get("dataset_version")
    if pinned_version and pinned_version != DATASET_VERSION:
        raise DatasetIntegrityError(
            f"MANIFEST dataset_version {pinned_version!r} does not match "
            f"package DATASET_VERSION {DATASET_VERSION!r}"
        )

    n_cases = pinned.get("n_cases")
    if isinstance(n_cases, int):
        line_count = sum(1 for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip())
        if line_count != n_cases:
            raise DatasetIntegrityError(
                f"Dataset case count {line_count} does not match MANIFEST n_cases {n_cases}"
            )

    return {
        "verified": True,
        "dataset_path": str(dataset_path.as_posix()),
        "manifest_path": str(pinned_path.as_posix()),
        "dataset_sha256": observed,
        "dataset_version": pinned_version,
        "n_cases": n_cases,
    }


def load_dataset(path: Path = DEFAULT_DATASET) -> list[FinanceCase]:
    cases: list[FinanceCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(FinanceCase.model_validate_json(line))
    return cases


def offline_candidate(case: FinanceCase) -> str:
    """Use embedded candidate_response for reproducible offline runs."""
    return case.candidate_response


def gold_candidate(case: FinanceCase) -> str:
    """Oracle responder using expected_answer — for baseline establishment only."""
    return case.expected_answer


def _normalize_call(raw: str | ModelCallResult) -> ModelCallResult:
    if isinstance(raw, ModelCallResult):
        return raw
    return ModelCallResult(text=raw)


def run_evaluation(
    *,
    dataset_path: Path = DEFAULT_DATASET,
    manifest_path: Path | None = None,
    model: str = "offline-candidate-fixture",
    model_version: str = "v1",
    prompt_version: str = PROMPT_VERSION,
    response_fn: ResponseFn | None = None,
    baseline_path: Path | None = DEFAULT_BASELINE,
    evidence_dir: Path = DEFAULT_EVIDENCE,
    reviews_path: Path = DEFAULT_REVIEWS,
    seed_reviews: bool = True,
    write_baseline: bool = False,
    mode: str = "candidate",
    limit: int | None = None,
    live_client: LiveModelClient | None = None,
    live_summary_path: Path | None = None,
) -> dict[str, Any]:
    stopped_reason: str | None = None
    live_budget_info: dict[str, Any] | None = None

    # Fail closed before any grading or model calls.
    integrity = verify_dataset_integrity(dataset_path, manifest_path=manifest_path)

    if live_client is not None:
        response_fn = live_client.complete
        model = live_client.model
        model_version = f"{live_client.provider}:{live_client.model}"
        limit = limit if limit is not None else live_client.budget.limit
        live_budget_info = {
            "max_cost_usd": live_client.budget.max_cost_usd,
            "max_retries": live_client.budget.max_retries,
            "timeout_s": live_client.budget.timeout_s,
            "limit": limit,
            "pricing_note": "estimated USD from static PRICE_PER_1M table — not invoices",
        }
    elif response_fn is None:
        response_fn = gold_candidate if mode == "gold" else offline_candidate
        if mode == "gold":
            model = "oracle-expected-answer"
            model_version = "gold"

    cases = load_dataset(dataset_path)
    if limit is not None:
        cases = cases[: max(0, limit)]

    results: list[CaseResult] = []
    for case in cases:
        try:
            call = _normalize_call(response_fn(case))
        except CostCapExceeded as exc:
            stopped_reason = str(exc)
            break

        graded = grade_case(case, call.text)
        failure_codes = list(graded["failure_codes"])
        detail = dict(graded["detail"])
        if call.error:
            detail["provider_error"] = call.error
            detail["retries"] = call.retries
            if graded["passed"] is False and F.FIN_NONE.value in failure_codes:
                failure_codes = [F.FIN_INST_014.value]
            elif call.error and not call.text.strip():
                failure_codes = [F.FIN_INST_014.value]
                graded = {"passed": False, "score": 0.0, "failure_codes": failure_codes, "detail": detail}

        item = CaseResult(
            case_id=case.case_id,
            category=case.category,
            difficulty=case.difficulty,
            passed=bool(graded["passed"]) and not (call.error and not call.text.strip()),
            score=0.0 if (call.error and not call.text.strip()) else float(graded["score"]),
            failure_codes=failure_codes if not (call.error and not call.text.strip()) else [F.FIN_INST_014.value],
            deterministic_detail=detail,
            # Always record the fixture label for audit; detection metrics use it
            # only when scoring the offline candidate responses (see below).
            planted_failure=case.planted_failure,
            latency_ms=call.latency_ms,
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            estimated_cost_usd=call.estimated_cost_usd,
        )
        item = attach_judge(case, call.text, item)
        results.append(item)

    if live_client is not None:
        live_budget_info = live_budget_info or {}
        live_budget_info["spent_usd"] = live_client.budget.spent_usd

    # Planted-detection metrics are meaningful only for offline candidate fixtures:
    # the labels describe the embedded candidate_response, not gold or live answers.
    compute_detection = live_client is None and mode == "candidate"
    metrics = aggregate_metrics(results, compute_planted_detection=compute_detection)
    metrics_dict = metrics_to_dict(metrics)
    result_dicts = [r.model_dump() for r in results]

    if seed_reviews:
        seed_human_reviews(result_dicts, reviews_path, sample_n=min(20, len(result_dicts)))
    reviews = load_reviews(reviews_path)
    pairs: list[tuple[str, str]] = []
    for r in result_dicts:
        human = reviews.get(r["case_id"])
        if not human:
            continue
        r["human_review"] = human
        judge_dec = (r.get("judge") or {}).get("decision")
        if judge_dec and human.get("decision"):
            pairs.append((str(judge_dec), str(human["decision"])))
    agree = agreement_rate(pairs)

    regression = None
    if baseline_path and baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        regression = compare_to_baseline(metrics, baseline)

    policy = evaluate_policy(metrics, regression)
    human_status = "SEEDED_PARTIAL" if reviews else "NONE"
    dataset_hash = integrity["dataset_sha256"]

    extra_manifest: dict[str, Any] = {
        "dataset_integrity": integrity,
    }
    if live_budget_info is not None:
        extra_manifest["live_budget"] = {
            **live_budget_info,
            "spent_usd": live_client.budget.spent_usd if live_client else live_budget_info.get("spent_usd"),
        }
        extra_manifest["maturity_labels"] = {
            "live_model_runner": "implemented",
            "cost_figures": "estimated",
        }
    if stopped_reason:
        extra_manifest["stopped_reason"] = stopped_reason

    manifest = write_evidence_bundle(
        evidence_dir,
        model=model,
        model_version=model_version,
        prompt_version=prompt_version,
        dataset_version=DATASET_VERSION,
        dataset_hash=dataset_hash,
        metrics=metrics_dict,
        case_results=result_dicts,
        policy=policy,
        regression=regression,
        human_review_status=human_status,
        extra=extra_manifest or None,
    )

    if write_baseline:
        out_baseline = baseline_path or DEFAULT_BASELINE
        out_baseline.parent.mkdir(parents=True, exist_ok=True)
        out_baseline.write_text(
            json.dumps(
                {
                    **metrics_dict,
                    "dataset_version": DATASET_VERSION,
                    "dataset_sha256": dataset_hash,
                    "model": model,
                    "model_version": model_version,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    out: dict[str, Any] = {
        "manifest": manifest,
        "metrics": metrics_dict,
        "policy": policy,
        "regression": regression,
        "judge_human_agreement": agree,
        "n_human_reviews": len(reviews),
        "n_cases": len(results),
        "live_budget": live_budget_info,
        "stopped_reason": stopped_reason,
    }

    if live_summary_path is not None:
        write_redacted_live_summary(live_summary_path, out)
    elif live_client is not None:
        write_redacted_live_summary(DEFAULT_LIVE_SUMMARY, out)

    return out

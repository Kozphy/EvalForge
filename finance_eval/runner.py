"""Finance evaluation runner: dataset → grade → judge → review → policy → evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from finance_eval import DATASET_VERSION, PROMPT_VERSION
from finance_eval.evidence import write_evidence_bundle
from finance_eval.graders import grade_case
from finance_eval.human_review import agreement_rate, is_independent_human, load_reviews, seed_demo_reviews
from finance_eval.judge import IndependentJudgeFn, attach_judge, judge_is_independent
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
DEFAULT_BASELINE = ROOT / "baselines" / "baseline_metrics.json"
DEFAULT_EVIDENCE = ROOT / "output" / "evidence"
DEFAULT_REVIEWS = ROOT / "output" / "human_reviews.jsonl"
DEFAULT_LIVE_SUMMARY = ROOT / "baselines" / "live_run_summary.example.json"
# Mock-provider runs are plumbing checks, not live-model evidence: keep their summary in the
# gitignored output directory so they never rewrite the tracked example above.
DEFAULT_MOCK_LIVE_SUMMARY = ROOT / "output" / "live_run_summary.mock.json"

PLANTED_LABEL_SOURCE = (
    "dataset planted_failure field (author-defined expected outcome per case; "
    "independent of grader output, not independent human labels)"
)
GOLD_LABEL_SOURCE = "gold mode: every expected answer is labeled as should-pass"

ResponseFn = Callable[[FinanceCase], str | ModelCallResult]


class DatasetIntegrityError(ValueError):
    """Dataset bytes, manifest, or case list failed verification; nothing was evaluated."""


def _load_dataset_snapshot(path: Path) -> tuple[list[FinanceCase], str]:
    """Verify the pinned manifest before parsing or making any model calls.

    A checked-in manifest is a consistency anchor, not a signature or proof that
    dataset and manifest were not both replaced by an actor with write access.
    """
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    manifest_path = path.with_name("MANIFEST.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetIntegrityError(f"missing dataset manifest: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetIntegrityError(f"malformed dataset manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict) or manifest.get("sha256") != digest:
        raise DatasetIntegrityError("dataset SHA-256 does not match MANIFEST.json")
    if manifest.get("dataset_version") != DATASET_VERSION:
        raise DatasetIntegrityError("unsupported dataset version")
    cases = [
        FinanceCase.model_validate_json(line)
        for line in raw.decode("utf-8").splitlines()
        if line.strip()
    ]
    if type(manifest.get("n_cases")) is not int or manifest["n_cases"] != len(cases):
        raise DatasetIntegrityError("dataset count does not match MANIFEST.json")
    if any(case.dataset_version != manifest["dataset_version"] for case in cases):
        raise DatasetIntegrityError("case dataset version does not match MANIFEST.json")
    if len({case.case_id for case in cases}) != len(cases):
        raise DatasetIntegrityError("duplicate dataset case ids")
    return cases, digest


def load_dataset(path: Path = DEFAULT_DATASET) -> list[FinanceCase]:
    """Load a dataset only when its sibling manifest matches the exact bytes."""
    return _load_dataset_snapshot(path)[0]


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
    model: str = "offline-candidate-fixture",
    model_version: str = "v1",
    prompt_version: str = PROMPT_VERSION,
    response_fn: ResponseFn | None = None,
    baseline_path: Path | None = DEFAULT_BASELINE,
    evidence_dir: Path = DEFAULT_EVIDENCE,
    reviews_path: Path = DEFAULT_REVIEWS,
    seed_reviews: bool = False,
    write_baseline: bool = False,
    mode: str = "candidate",
    limit: int | None = None,
    live_client: LiveModelClient | None = None,
    live_summary_path: Path | None = None,
    judge_fn: IndependentJudgeFn | None = None,
) -> dict[str, Any]:
    stopped_reason: str | None = None
    # Reference labels exist only for the built-in offline fixtures, whose responses the
    # dataset describes. Live, mock and custom response functions get no labels.
    reference_mode: str | None = None
    live_budget_info: dict[str, Any] | None = None

    if live_client is not None:
        response_fn = live_client.complete
        model = live_client.model
        model_version = f"{live_client.provider}:{live_client.model}"
        limit = limit if limit is not None else live_client.budget.limit
        live_budget_info = {
            "provider": live_client.provider,
            "paid": live_client.provider in {"openai", "anthropic"},
            "replayed_from_sha256": live_client.replay_sha256,
            "max_cost_usd": live_client.budget.max_cost_usd,
            "max_retries": live_client.budget.max_retries,
            "timeout_s": live_client.budget.timeout_s,
            "limit": limit,
            "pricing_note": "estimated USD from static PRICE_PER_1M table — not invoices",
        }
    elif response_fn is None:
        reference_mode = "gold" if mode == "gold" else "planted"
        response_fn = gold_candidate if mode == "gold" else offline_candidate
        if mode == "gold":
            model = "oracle-expected-answer"
            model_version = "gold"

    cases, dataset_hash = _load_dataset_snapshot(dataset_path)
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
            latency_ms=call.latency_ms,
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            estimated_cost_usd=call.estimated_cost_usd,
        )
        item = attach_judge(case, call.text, item, judge_fn=judge_fn)
        results.append(item)

    if live_client is not None:
        live_budget_info = live_budget_info or {}
        live_budget_info["spent_usd"] = live_client.budget.spent_usd

    reference_pass: dict[str, bool] | None = None
    label_source: str | None = None
    if reference_mode is not None:
        by_id = {case.case_id: case for case in cases}
        if reference_mode == "gold":
            reference_pass = {r.case_id: True for r in results}
            label_source = GOLD_LABEL_SOURCE
        else:
            reference_pass = {r.case_id: by_id[r.case_id].planted_failure == F.FIN_NONE.value for r in results}
            label_source = PLANTED_LABEL_SOURCE
    metrics = aggregate_metrics(results, reference_pass=reference_pass, reference_label_source=label_source)
    metrics_dict = metrics_to_dict(metrics)
    result_dicts = [r.model_dump() for r in results]

    if seed_reviews:
        seed_demo_reviews(result_dicts, reviews_path, sample_n=min(20, len(result_dicts)))
    reviews = load_reviews(reviews_path)
    pairs: list[tuple[str, str]] = []
    for r in result_dicts:
        human = reviews.get(r["case_id"])
        if not human:
            continue
        if not is_independent_human(human):
            r["demo_review"] = human
            continue
        r["human_review"] = human
        judge = r.get("judge") or {}
        judge_dec = judge.get("decision")
        # Agreement with a judge that copies the grader carries no information.
        if judge_dec and human.get("decision") and judge_is_independent(judge):
            pairs.append((str(judge_dec), str(human["decision"])))
    agree = agreement_rate(pairs)
    judge_independent = bool(result_dicts) and all(judge_is_independent(r.get("judge")) for r in result_dicts)
    agreement_note = None if judge_independent else "not computed: judge is not independent of the deterministic grader"

    regression = None
    if baseline_path and baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        regression = compare_to_baseline(metrics, baseline)

    policy = evaluate_policy(metrics, regression)
    n_independent = sum(1 for row in reviews.values() if is_independent_human(row))
    n_seeded = len(reviews) - n_independent
    if n_independent:
        human_status = "INDEPENDENT_PARTIAL"
    elif n_seeded:
        human_status = "SEEDED_DEMO_ONLY_NO_HUMAN_REVIEW"
    else:
        human_status = "NONE"

    extra_manifest: dict[str, Any] = {}
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
        "judge_independent": judge_independent,
        "judge_human_agreement_note": agreement_note,
        "n_human_reviews": n_independent,
        "n_seeded_demo_reviews": n_seeded,
        "n_cases": len(results),
        "live_budget": live_budget_info,
        "stopped_reason": stopped_reason,
    }

    if live_summary_path is not None:
        write_redacted_live_summary(live_summary_path, out)

    return out

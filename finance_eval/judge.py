"""Optional LLM-as-a-judge — never sole source of truth."""

from __future__ import annotations

from typing import Any, Callable

from finance_eval.schema import CaseResult, FinanceCase

# A judge that only sees the case and the response — never the deterministic outcome.
IndependentJudgeFn = Callable[[FinanceCase, str], dict[str, Any]]

MIRROR_SOURCES = frozenset({"simulated_heuristic_judge"})


def judge_is_independent(judge: dict[str, Any] | None) -> bool:
    """True only for judges that did not derive their verdict from the grader."""
    if not judge:
        return False
    return judge.get("independent") is True and judge.get("source") not in MIRROR_SOURCES


def heuristic_judge(case: FinanceCase, response: str, deterministic: dict[str, Any]) -> dict[str, Any]:
    """Lightweight rubric scores derived from deterministic outcome.

    This is explicitly *not* an LLM call. It exists so the pipeline shape
    (deterministic → judge → human) is complete offline. Label: simulated.
    """
    passed = bool(deterministic.get("passed"))
    base = 5 if passed else 2
    return {
        "source": "simulated_heuristic_judge",
        "independent": False,
        "derived_from": "deterministic_grader",
        "correctness": base,
        "reasoning": base if passed else 2,
        "completeness": 4 if passed else 2,
        "domain_validity": 5 if passed else 2,
        "evidence_quality": 4 if case.required_evidence and passed else (2 if case.required_evidence else 3),
        "financial_risk": "low" if passed else ("critical" if any("AUD" in c or "HALL" in c or "JE" in c for c in deterministic.get("failure_codes", [])) else "high"),
        "decision": "pass" if passed else "fail",
        "notes": "Judge scores mirrored from deterministic checks — not independent LLM judgment.",
    }


def attach_judge(
    case: FinanceCase,
    response: str,
    result: CaseResult,
    judge_fn: IndependentJudgeFn | None = None,
) -> CaseResult:
    if judge_fn is None:
        result.judge = heuristic_judge(case, response, result.deterministic_detail | {
            "passed": result.passed,
            "failure_codes": result.failure_codes,
        })
        return result
    verdict = dict(judge_fn(case, response))
    if verdict.get("decision") not in {"pass", "fail"}:
        raise ValueError("independent judge must return decision 'pass' or 'fail'")
    if verdict.get("source") in MIRROR_SOURCES or not verdict.get("source"):
        raise ValueError("independent judge must declare a non-mirror source")
    verdict["independent"] = True
    result.judge = verdict
    return result

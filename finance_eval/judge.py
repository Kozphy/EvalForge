"""Optional LLM-as-a-judge — never sole source of truth."""

from __future__ import annotations

from typing import Any

from finance_eval.schema import CaseResult, FinanceCase


def heuristic_judge(case: FinanceCase, response: str, deterministic: dict[str, Any]) -> dict[str, Any]:
    """Lightweight rubric scores derived from deterministic outcome.

    This is explicitly *not* an LLM call. It exists so the pipeline shape
    (deterministic → judge → human) is complete offline. Label: simulated.
    """
    passed = bool(deterministic.get("passed"))
    base = 5 if passed else 2
    return {
        "source": "simulated_heuristic_judge",
        "correctness": base,
        "reasoning": base if passed else 2,
        "completeness": 4 if passed else 2,
        "domain_validity": 5 if passed else 2,
        "evidence_quality": 4 if case.required_evidence and passed else (2 if case.required_evidence else 3),
        "financial_risk": "low" if passed else ("critical" if any("AUD" in c or "HALL" in c or "JE" in c for c in deterministic.get("failure_codes", [])) else "high"),
        "decision": "pass" if passed else "fail",
        "notes": "Judge scores mirrored from deterministic checks — not independent LLM judgment.",
    }


def attach_judge(case: FinanceCase, response: str, result: CaseResult) -> CaseResult:
    result.judge = heuristic_judge(case, response, result.deterministic_detail | {
        "passed": result.passed,
        "failure_codes": result.failure_codes,
    })
    return result

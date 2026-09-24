"""Deterministic graders — primary source of truth for finance_eval CI."""

from __future__ import annotations

import json
import re
from typing import Any

from finance_eval.schema import FinanceCase, GradeMode
from finance_eval.taxonomy import FinanceFailureCode as F


_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def extract_number(text: str) -> float | None:
    matches = _NUM_RE.findall(text.replace(",", ""))
    if not matches:
        return None
    try:
        return float(matches[0])
    except ValueError:
        return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _journal_totals(side: list[dict[str, Any]]) -> float:
    return sum(float(item.get("amount", 0)) for item in side)


def _accounts(side: list[dict[str, Any]]) -> set[str]:
    return {_norm(str(item.get("account", ""))) for item in side}


def grade_case(case: FinanceCase, response: str) -> dict[str, Any]:
    gold = case.structured_golden
    mode = gold.mode
    tol = gold.tolerance if gold.tolerance is not None else case.allowed_tolerance or 0.0
    detail: dict[str, Any] = {"mode": mode.value}
    failures: list[str] = []
    score = 0.0
    passed = False

    if mode == GradeMode.NUMERIC:
        observed = extract_number(response)
        expected = float(gold.value)
        detail.update({"expected": expected, "observed": observed, "tolerance": tol})
        if observed is None:
            failures.append(F.FIN_INST_014.value)
        elif abs(observed - expected) <= tol:
            passed, score = True, 1.0
        elif case.category == "reconciliation":
            failures.append(F.FIN_RECON_013.value)
        else:
            failures.append(F.FIN_CALC_001.value)

    elif mode == GradeMode.EXACT_TEXT:
        expected = _norm(str(gold.value))
        observed = _norm(response)
        detail.update({"expected": expected, "observed": observed})
        if observed == expected:
            passed, score = True, 1.0
        else:
            # Prefer domain failures from planted taxonomy hints when clear
            if case.category in {"revenue_recognition"} and expected in {"yes", "no", "true", "false"}:
                failures.append(F.FIN_REV_010.value if "rev" in case.case_id.casefold() or case.category == "revenue_recognition" else F.FIN_ACC_002.value)
            elif case.category == "cash_flow":
                failures.append(F.FIN_CF_003.value)
            elif case.category in {"audit_reasoning"}:
                failures.append(F.FIN_AUD_004.value)
            elif case.category == "internal_controls":
                failures.append(F.FIN_CTRL_012.value)
            elif case.category == "anomaly_detection":
                failures.append(F.FIN_HALL_006.value)
            elif " " in response.strip() and expected.isdigit():
                failures.append(F.FIN_INST_014.value)
            else:
                failures.append(F.FIN_ACC_002.value)

    elif mode == GradeMode.CONTAINS_ALL:
        required = [_norm(x) for x in gold.value]
        hay = _norm(response)
        missing = [r for r in required if r not in hay]
        detail.update({"required": required, "missing": missing})
        if not missing and "definitely" not in hay:
            passed, score = True, 1.0
        else:
            failures.append(F.FIN_EVID_009.value)

    elif mode == GradeMode.MULTI_CHOICE:
        expected = _norm(str(gold.value))
        observed = _norm(response)
        detail.update({"expected": expected, "observed": observed})
        if observed == expected:
            passed, score = True, 1.0
        else:
            failures.append(F.FIN_ACC_002.value)

    elif mode == GradeMode.JOURNAL_JSON:
        try:
            payload = json.loads(response)
        except json.JSONDecodeError as exc:
            detail["error"] = str(exc)
            failures.append(F.FIN_INST_014.value)
            return {"passed": False, "score": 0.0, "failure_codes": failures, "detail": detail}
        debits = payload.get("debits") or []
        credits = payload.get("credits") or []
        dt, ct = _journal_totals(debits), _journal_totals(credits)
        detail.update({"debit_total": dt, "credit_total": ct})
        if abs(dt - ct) > (tol or 0.01):
            failures.append(F.FIN_JE_011.value)
        expected = gold.value
        exp_d = _accounts(expected.get("debits", []))
        exp_c = _accounts(expected.get("credits", []))
        obs_d, obs_c = _accounts(debits), _accounts(credits)
        detail.update({"expected_debit_accounts": sorted(exp_d), "observed_debit_accounts": sorted(obs_d)})
        amounts_ok = abs(dt - _journal_totals(expected.get("debits", []))) <= (tol or 0.01)
        accounts_ok = exp_d == obs_d and exp_c == obs_c
        if not accounts_ok:
            # revenue vs unearned mistakes
            joined = " ".join(sorted(obs_d | obs_c))
            if "revenue" in joined and "unearned" in " ".join(sorted(exp_d | exp_c)):
                failures.append(F.FIN_REV_010.value)
            else:
                failures.append(F.FIN_ACC_002.value if F.FIN_JE_011.value not in failures else F.FIN_JE_011.value)
        if abs(dt - ct) <= (tol or 0.01) and accounts_ok and amounts_ok:
            passed, score = True, 1.0
            failures = []

    elif mode in {GradeMode.SQL_RESULT, GradeMode.PYTHON_RESULT}:
        expected = float(gold.value["result"])
        observed = extract_number(response)
        detail.update({"expected": expected, "observed": observed, "tolerance": tol})
        if observed is None:
            failures.append(F.FIN_INST_014.value)
        elif abs(observed - expected) <= (tol or 0.01):
            passed, score = True, 1.0
        else:
            failures.append(F.FIN_SQL_007.value if mode == GradeMode.SQL_RESULT else F.FIN_PY_008.value)

    else:
        failures.append(F.FIN_INST_014.value)

    if passed:
        failures = [F.FIN_NONE.value]

    return {
        "passed": passed,
        "score": score,
        "failure_codes": failures,
        "detail": detail,
    }

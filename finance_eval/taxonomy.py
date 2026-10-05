"""Machine-readable finance failure taxonomy."""

from __future__ import annotations

from enum import Enum
from typing import Any


class FinanceFailureCode(str, Enum):
    FIN_CALC_001 = "FIN-CALC-001"  # arithmetic error
    FIN_ACC_002 = "FIN-ACC-002"  # accounting classification error
    FIN_CF_003 = "FIN-CF-003"  # cash-flow / profit confusion
    FIN_AUD_004 = "FIN-AUD-004"  # unsupported audit conclusion
    FIN_RATIO_005 = "FIN-RATIO-005"  # incorrect ratio interpretation
    FIN_HALL_006 = "FIN-HALL-006"  # fabricated financial fact
    FIN_SQL_007 = "FIN-SQL-007"  # incorrect aggregation or join
    FIN_PY_008 = "FIN-PY-008"  # incorrect financial calculation (code)
    FIN_EVID_009 = "FIN-EVID-009"  # conclusion unsupported by evidence
    FIN_REV_010 = "FIN-REV-010"  # revenue recognition error
    FIN_JE_011 = "FIN-JE-011"  # journal entry imbalance / wrong accounts
    FIN_CTRL_012 = "FIN-CTRL-012"  # internal control reasoning error
    FIN_RECON_013 = "FIN-RECON-013"  # reconciliation error
    FIN_INST_014 = "FIN-INST-014"  # instruction-following failure
    FIN_NONE = "FIN-NONE"  # no failure / pass


TAXONOMY: dict[str, dict[str, Any]] = {
    FinanceFailureCode.FIN_CALC_001.value: {
        "name": "arithmetic_error",
        "severity_default": "high",
        "description": "Numeric arithmetic does not match inputs within tolerance.",
    },
    FinanceFailureCode.FIN_ACC_002.value: {
        "name": "accounting_classification_error",
        "severity_default": "high",
        "description": "Wrong account class (asset/liability/equity/revenue/expense).",
    },
    FinanceFailureCode.FIN_CF_003.value: {
        "name": "cash_flow_profit_confusion",
        "severity_default": "critical",
        "description": "Confuses accrual profit with cash movement.",
    },
    FinanceFailureCode.FIN_AUD_004.value: {
        "name": "unsupported_audit_conclusion",
        "severity_default": "critical",
        "description": "Audit conclusion not supported by stated evidence.",
    },
    FinanceFailureCode.FIN_RATIO_005.value: {
        "name": "incorrect_ratio_interpretation",
        "severity_default": "medium",
        "description": "Ratio formula or interpretation is wrong.",
    },
    FinanceFailureCode.FIN_HALL_006.value: {
        "name": "fabricated_financial_fact",
        "severity_default": "critical",
        "description": "Invented amounts, standards, or entity facts.",
    },
    FinanceFailureCode.FIN_SQL_007.value: {
        "name": "incorrect_sql_aggregation_or_join",
        "severity_default": "high",
        "description": "SQL produces wrong aggregation, filter, or join.",
    },
    FinanceFailureCode.FIN_PY_008.value: {
        "name": "incorrect_python_financial_calc",
        "severity_default": "high",
        "description": "Python code computes wrong financial result.",
    },
    FinanceFailureCode.FIN_EVID_009.value: {
        "name": "unsupported_by_evidence",
        "severity_default": "high",
        "description": "Conclusion lacks required evidence references.",
    },
    FinanceFailureCode.FIN_REV_010.value: {
        "name": "revenue_recognition_error",
        "severity_default": "critical",
        "description": "Incorrect timing or amount of revenue recognition.",
    },
    FinanceFailureCode.FIN_JE_011.value: {
        "name": "journal_entry_error",
        "severity_default": "critical",
        "description": "Unbalanced entry or wrong debit/credit accounts.",
    },
    FinanceFailureCode.FIN_CTRL_012.value: {
        "name": "internal_control_reasoning_error",
        "severity_default": "medium",
        "description": "Misstates control purpose, weakness, or remediation.",
    },
    FinanceFailureCode.FIN_RECON_013.value: {
        "name": "reconciliation_error",
        "severity_default": "high",
        "description": "Incorrect reconciling items or ending balance.",
    },
    FinanceFailureCode.FIN_INST_014.value: {
        "name": "instruction_following_failure",
        "severity_default": "low",
        "description": "Ignored required format, units, or output schema.",
    },
    FinanceFailureCode.FIN_NONE.value: {
        "name": "pass",
        "severity_default": "none",
        "description": "No domain failure detected by deterministic checks.",
    },
}


def taxonomy_catalog() -> list[dict[str, Any]]:
    return [
        {"code": code, **meta}
        for code, meta in TAXONOMY.items()
    ]


def is_critical(code: str) -> bool:
    meta = TAXONOMY.get(code) or {}
    return meta.get("severity_default") == "critical"

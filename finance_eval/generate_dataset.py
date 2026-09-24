"""Generate original finance-accounting-v1 golden set (frozen JSONL).

Items are synthetic teaching cases — not reproduced from copyrighted exams.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from finance_eval import DATASET_VERSION
from finance_eval.schema import (
    FinanceCase,
    GoldenAnswer,
    GradeMode,
    GradingRubric,
)
from finance_eval.taxonomy import FinanceFailureCode as F

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dataset" / f"{DATASET_VERSION.replace('-', '_')}.jsonl"
MANIFEST = ROOT / "dataset" / "MANIFEST.json"


def _rubric(correct: str, fail: str, partial: str | None = None) -> GradingRubric:
    return GradingRubric(correct_if=correct, fail_if=fail, partial_credit=partial)


def _case(**kwargs) -> FinanceCase:
    kwargs.setdefault("dataset_version", DATASET_VERSION)
    return FinanceCase(**kwargs)


def build_cases() -> list[FinanceCase]:
    cases: list[FinanceCase] = []
    n = 0

    def add(case: FinanceCase) -> None:
        nonlocal n
        n += 1
        cases.append(case)

    # --- Accounting equations (10) ---
    for i, (a, l, e, ok) in enumerate(
        [
            (100_000, 40_000, 60_000, True),
            (250_000, 90_000, 160_000, True),
            (80_000, 50_000, 20_000, False),  # should be 30k equity
            (500_000, 200_000, 300_000, True),
            (75_000, 25_000, 50_000, True),
            (120_000, 70_000, 40_000, False),
            (1_000_000, 400_000, 600_000, True),
            (45_000, 15_000, 30_000, True),
            (90_000, 60_000, 40_000, False),
            (33_000, 11_000, 22_000, True),
        ],
        start=1,
    ):
        eq = a - l
        planted = F.FIN_NONE.value if ok else F.FIN_ACC_002.value
        cand = str(e if ok else e)  # candidate states equity claim
        # For failing planted cases, candidate asserts wrong equity as if correct
        expected = str(eq)
        add(
            _case(
                case_id=f"EQ-{i:03d}",
                category="accounting_equations",
                difficulty="easy",
                question=(
                    f"Assets = {a:,}, Liabilities = {l:,}. "
                    "What is equity? Reply with a number only."
                ),
                expected_answer=expected,
                structured_golden=GoldenAnswer(
                    mode=GradeMode.NUMERIC, value=float(eq), tolerance=0.01, unit="USD"
                ),
                grading_rubric=_rubric(
                    "Equity equals Assets minus Liabilities within $0.01.",
                    "Wrong equity or non-numeric answer.",
                ),
                allowed_tolerance=0.01,
                required_evidence=["accounting_equation"],
                known_failure_modes=[F.FIN_CALC_001.value, F.FIN_ACC_002.value],
                tags=["equation", "equity"],
                candidate_response=str(e) if not ok else expected,
                planted_failure=planted if not ok else F.FIN_NONE.value,
            )
        )

    # --- Journal entries (12) ---
    journals = [
        (
            "Purchase inventory $5,000 on account.",
            {"debits": [{"account": "Inventory", "amount": 5000}], "credits": [{"account": "Accounts Payable", "amount": 5000}]},
            True,
            '{"debits":[{"account":"Inventory","amount":5000}],"credits":[{"account":"Accounts Payable","amount":5000}]}',
        ),
        (
            "Pay $2,000 cash for rent expense.",
            {"debits": [{"account": "Rent Expense", "amount": 2000}], "credits": [{"account": "Cash", "amount": 2000}]},
            True,
            '{"debits":[{"account":"Rent Expense","amount":2000}],"credits":[{"account":"Cash","amount":2000}]}',
        ),
        (
            "Owner invests $10,000 cash.",
            {"debits": [{"account": "Cash", "amount": 10000}], "credits": [{"account": "Owner Equity", "amount": 10000}]},
            True,
            '{"debits":[{"account":"Cash","amount":10000}],"credits":[{"account":"Owner Equity","amount":10000}]}',
        ),
        (
            "Collect $1,500 of accounts receivable in cash.",
            {"debits": [{"account": "Cash", "amount": 1500}], "credits": [{"account": "Accounts Receivable", "amount": 1500}]},
            True,
            '{"debits":[{"account":"Cash","amount":1500}],"credits":[{"account":"Accounts Receivable","amount":1500}]}',
        ),
        (
            "Record $800 depreciation of equipment.",
            {"debits": [{"account": "Depreciation Expense", "amount": 800}], "credits": [{"account": "Accumulated Depreciation", "amount": 800}]},
            True,
            '{"debits":[{"account":"Depreciation Expense","amount":800}],"credits":[{"account":"Accumulated Depreciation","amount":800}]}',
        ),
        (
            "Buy equipment $12,000 paying $4,000 cash and the rest on note.",
            {
                "debits": [{"account": "Equipment", "amount": 12000}],
                "credits": [
                    {"account": "Cash", "amount": 4000},
                    {"account": "Notes Payable", "amount": 8000},
                ],
            },
            True,
            '{"debits":[{"account":"Equipment","amount":12000}],"credits":[{"account":"Cash","amount":4000},{"account":"Notes Payable","amount":8000}]}',
        ),
    ]
    for i, (desc, gold, ok, cand) in enumerate(journals, start=1):
        add(
            _case(
                case_id=f"JE-{i:03d}",
                category="journal_entries",
                difficulty="medium",
                question=(
                    f"{desc} Return JSON with keys debits and credits; "
                    "each item has account and amount. Debits must equal credits."
                ),
                expected_answer=json.dumps(gold, separators=(",", ":")),
                structured_golden=GoldenAnswer(mode=GradeMode.JOURNAL_JSON, value=gold, tolerance=0.01),
                grading_rubric=_rubric(
                    "Balanced entry with correct accounts and amounts.",
                    "Unbalanced entry, wrong accounts, or invalid JSON.",
                ),
                allowed_tolerance=0.01,
                required_evidence=["double_entry"],
                known_failure_modes=[F.FIN_JE_011.value, F.FIN_ACC_002.value],
                tags=["journal"],
                candidate_response=cand,
                planted_failure=F.FIN_NONE.value,
            )
        )
    # Planted unbalanced / wrong account journals
    bad_journals = [
        (
            "JE-007",
            "Sell services for $3,000 cash.",
            {"debits": [{"account": "Cash", "amount": 3000}], "credits": [{"account": "Service Revenue", "amount": 3000}]},
            '{"debits":[{"account":"Cash","amount":3000}],"credits":[{"account":"Service Revenue","amount":2500}]}',
            F.FIN_JE_011.value,
        ),
        (
            "JE-008",
            "Pay $500 of accounts payable in cash.",
            {"debits": [{"account": "Accounts Payable", "amount": 500}], "credits": [{"account": "Cash", "amount": 500}]},
            '{"debits":[{"account":"Accounts Receivable","amount":500}],"credits":[{"account":"Cash","amount":500}]}',
            F.FIN_ACC_002.value,
        ),
        (
            "JE-009",
            "Accrue $900 wages payable.",
            {"debits": [{"account": "Wages Expense", "amount": 900}], "credits": [{"account": "Wages Payable", "amount": 900}]},
            '{"debits":[{"account":"Wages Payable","amount":900}],"credits":[{"account":"Wages Expense","amount":900}]}',
            F.FIN_JE_011.value,
        ),
        (
            "JE-010",
            "Declare $1,200 cash dividend (declare only).",
            {"debits": [{"account": "Retained Earnings", "amount": 1200}], "credits": [{"account": "Dividends Payable", "amount": 1200}]},
            '{"debits":[{"account":"Dividends Payable","amount":1200}],"credits":[{"account":"Cash","amount":1200}]}',
            F.FIN_ACC_002.value,
        ),
        (
            "JE-011",
            "Receive $2,000 unearned revenue in cash.",
            {"debits": [{"account": "Cash", "amount": 2000}], "credits": [{"account": "Unearned Revenue", "amount": 2000}]},
            '{"debits":[{"account":"Cash","amount":2000}],"credits":[{"account":"Revenue","amount":2000}]}',
            F.FIN_REV_010.value,
        ),
        (
            "JE-012",
            "Adjust: earn $600 of previously unearned revenue.",
            {"debits": [{"account": "Unearned Revenue", "amount": 600}], "credits": [{"account": "Service Revenue", "amount": 600}]},
            '{"debits":[{"account":"Service Revenue","amount":600}],"credits":[{"account":"Unearned Revenue","amount":600}]}',
            F.FIN_REV_010.value,
        ),
    ]
    for cid, desc, gold, cand, fail in bad_journals:
        add(
            _case(
                case_id=cid,
                category="journal_entries",
                difficulty="medium",
                question=(
                    f"{desc} Return JSON with keys debits and credits; "
                    "each item has account and amount. Debits must equal credits."
                ),
                expected_answer=json.dumps(gold, separators=(",", ":")),
                structured_golden=GoldenAnswer(mode=GradeMode.JOURNAL_JSON, value=gold, tolerance=0.01),
                grading_rubric=_rubric(
                    "Balanced entry with correct accounts and amounts.",
                    "Unbalanced entry, wrong accounts, or invalid JSON.",
                ),
                allowed_tolerance=0.01,
                required_evidence=["double_entry"],
                known_failure_modes=[F.FIN_JE_011.value, F.FIN_ACC_002.value, F.FIN_REV_010.value],
                tags=["journal", "planted_error"],
                candidate_response=cand,
                planted_failure=fail,
            )
        )

    # --- Revenue recognition (10) ---
    rev_items = [
        ("REV-001", "Customer prepays $4,000 for services next month. Recognize revenue now?", "no", True, F.FIN_NONE),
        ("REV-002", "Goods delivered and control transferred; invoice $9,500. Recognize now?", "yes", True, F.FIN_NONE),
        ("REV-003", "Signed contract only; no performance yet. Recognize $50k?", "no", True, F.FIN_NONE),
        ("REV-004", "Performance obligation complete; cash not yet collected $2,200. Recognize?", "yes", True, F.FIN_NONE),
        ("REV-005", "Right of return highly uncertain; inventory shipped. Recognize full amount?", "no", True, F.FIN_NONE),
        ("REV-006", "Bill-and-hold: customer requested delay; control criteria unmet. Recognize?", "no", True, F.FIN_NONE),
        ("REV-007", "Agent arranges sale for principal; fee is $300. Recognize $10,000 gross?", "no", False, F.FIN_REV_010),
        ("REV-008", "Subscription month completed; monthly fee $99. Recognize $99?", "yes", True, F.FIN_NONE),
        ("REV-009", "Gift card sold $100; unused. Recognize revenue immediately?", "no", True, F.FIN_NONE),
        ("REV-010", "Candidate claims IFRS always allows cash-basis revenue for retailers.", "false", False, F.FIN_HALL_006),
    ]
    for cid, q, ans, ok, fail in rev_items:
        cand = ans if ok else ("yes" if ans == "no" else "true" if ans == "false" else "no")
        if cid == "REV-007":
            cand = "yes"  # wrongly recognizes gross
        if cid == "REV-010":
            cand = "true"
        add(
            _case(
                case_id=cid,
                category="revenue_recognition",
                difficulty="medium",
                question=f"{q} Answer with exactly: yes, no, true, or false as appropriate.",
                expected_answer=ans,
                structured_golden=GoldenAnswer(mode=GradeMode.EXACT_TEXT, value=ans),
                grading_rubric=_rubric(
                    "Matches expected yes/no/true/false on recognition timing/agent vs principal.",
                    "Incorrect recognition decision or fabricated standard claim.",
                ),
                required_evidence=["performance_obligation"],
                known_failure_modes=[F.FIN_REV_010.value, F.FIN_HALL_006.value],
                tags=["revenue"],
                candidate_response=cand,
                planted_failure=fail.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- Gross margin & expense (14) ---
    for i, (sales, cogs, ok_delta) in enumerate(
        [
            (200_000, 120_000, 0),
            (80_000, 50_000, 0),
            (15_000, 9_000, 0),
            (500_000, 275_000, 0),
            (42_000, 30_000, 0),
            (100_000, 60_000, 5),  # planted wrong margin
            (250_000, 100_000, 0),
            (90_000, 45_000, 0),
        ],
        start=1,
    ):
        margin = (sales - cogs) / sales
        cand_val = margin if ok_delta == 0 else margin + ok_delta / 100
        add(
            _case(
                case_id=f"GM-{i:03d}",
                category="gross_margin",
                difficulty="easy",
                question=(
                    f"Sales = {sales}, COGS = {cogs}. "
                    "What is gross margin ratio? Number between 0 and 1, 4 decimals."
                ),
                expected_answer=f"{margin:.4f}",
                structured_golden=GoldenAnswer(
                    mode=GradeMode.NUMERIC, value=round(margin, 6), tolerance=0.0005
                ),
                grading_rubric=_rubric(
                    "Gross margin = (Sales - COGS) / Sales within 0.0005.",
                    "Wrong formula or arithmetic.",
                ),
                allowed_tolerance=0.0005,
                required_evidence=["income_statement"],
                known_failure_modes=[F.FIN_CALC_001.value, F.FIN_RATIO_005.value],
                tags=["margin"],
                candidate_response=f"{cand_val:.4f}",
                planted_failure=F.FIN_CALC_001.value if ok_delta else F.FIN_NONE.value,
            )
        )

    expense_class = [
        ("EXP-001", "Office rent for HQ", "operating_expense", "operating_expense", True),
        ("EXP-002", "Interest on bank loan", "interest_expense", "interest_expense", True),
        ("EXP-003", "Purchase of delivery van", "capital_expenditure", "capital_expenditure", True),
        ("EXP-004", "Inventory purchase for resale", "inventory_asset", "inventory_asset", True),
        ("EXP-005", "Dividend paid to owners", "financing_distribution", "financing_distribution", True),
        ("EXP-006", "R&D salaries (expense policy)", "operating_expense", "capital_expenditure", False),
    ]
    for cid, item, gold, cand, ok in expense_class:
        add(
            _case(
                case_id=cid,
                category="expense_classification",
                difficulty="easy",
                question=(
                    f"Classify '{item}' as one of: operating_expense, interest_expense, "
                    "capital_expenditure, inventory_asset, financing_distribution."
                ),
                expected_answer=gold,
                structured_golden=GoldenAnswer(mode=GradeMode.EXACT_TEXT, value=gold),
                grading_rubric=_rubric("Exact class label match.", "Misclassification."),
                known_failure_modes=[F.FIN_ACC_002.value],
                tags=["classification"],
                candidate_response=cand,
                planted_failure=F.FIN_ACC_002.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- Cash flow (10) ---
    cf_items = [
        ("CF-001", "Depreciation expense effect on operating cash flow (indirect)?", "add_back", True),
        ("CF-002", "Increase in AR effect on operating cash (indirect)?", "subtract", True),
        ("CF-003", "Issuing stock for cash is which section?", "financing", True),
        ("CF-004", "Buying equipment for cash is which section?", "investing", True),
        ("CF-005", "Net income always equals operating cash flow?", "no", True),
        ("CF-006", "Paying a supplier reduces investing cash flow?", "no", True),
        ("CF-007", "Candidate equates higher NI with higher free cash flow always.", "false", False),
        ("CF-008", "Decrease in inventory (indirect) effect?", "add", True),
        ("CF-009", "Principal repayment of loan section?", "financing", True),
        ("CF-010", "Interest paid typically classified as?", "operating", True),
    ]
    for cid, q, ans, ok in cf_items:
        cand = ans if ok else ("yes" if ans == "no" else "true" if ans == "false" else "investing")
        if cid == "CF-007":
            cand = "true"
        add(
            _case(
                case_id=cid,
                category="cash_flow",
                difficulty="medium",
                question=f"{q} One-token answer from the expected vocabulary.",
                expected_answer=ans,
                structured_golden=GoldenAnswer(mode=GradeMode.EXACT_TEXT, value=ans),
                grading_rubric=_rubric(
                    "Correct cash-flow classification or adjustment direction.",
                    "Cash vs profit confusion or wrong section.",
                ),
                known_failure_modes=[F.FIN_CF_003.value],
                tags=["cash_flow"],
                candidate_response=cand,
                planted_failure=F.FIN_CF_003.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- Ratios (12) ---
    ratio_specs = [
        ("RAT-001", "Current assets 80k, current liabilities 40k. Current ratio?", 2.0, True),
        ("RAT-002", "CA 90k, CL 60k. Current ratio?", 1.5, True),
        ("RAT-003", "Net income 12k, equity 60k. ROE?", 0.2, True),
        ("RAT-004", "NI 25k, assets 200k. ROA?", 0.125, True),
        ("RAT-005", "Debt 70k, equity 30k. Debt-to-equity?", 2.3333, True),
        ("RAT-006", "Sales 100k, AR 20k. Receivables turnover?", 5.0, True),
        ("RAT-007", "COGS 60k, avg inventory 15k. Inventory turnover?", 4.0, True),
        ("RAT-008", "Quick assets 50k, CL 25k. Quick ratio?", 2.0, True),
        ("RAT-009", "GM 40k, sales 100k. GM ratio?", 0.4, True),
        ("RAT-010", "EBIT 30k, interest 10k. Interest coverage?", 3.0, True),
        ("RAT-011", "CA 100k, CL 100k. Current ratio? (planted as 2.0)", 1.0, False),
        ("RAT-012", "NI 10k, sales 200k. Net margin?", 0.05, True),
    ]
    for cid, q, val, ok in ratio_specs:
        cand = f"{(val if ok else 2.0):.4f}"
        add(
            _case(
                case_id=cid,
                category="financial_ratios",
                difficulty="easy",
                question=f"{q} Number only.",
                expected_answer=f"{val:.4f}",
                structured_golden=GoldenAnswer(mode=GradeMode.NUMERIC, value=float(val), tolerance=0.01),
                grading_rubric=_rubric("Correct ratio within 0.01.", "Wrong formula/interpretation."),
                allowed_tolerance=0.01,
                known_failure_modes=[F.FIN_RATIO_005.value, F.FIN_CALC_001.value],
                tags=["ratio"],
                candidate_response=cand,
                planted_failure=F.FIN_RATIO_005.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- Financial statements / analysis (10) ---
    fs_items = [
        ("FS-001", "Which statement shows financial position at a point in time?", "balance_sheet", True),
        ("FS-002", "Which statement shows performance over a period?", "income_statement", True),
        ("FS-003", "Retained earnings bridge appears primarily on?", "statement_of_equity", True),
        ("FS-004", "Unearned revenue is typically a?", "liability", True),
        ("FS-005", "Prepaid insurance is typically a?", "asset", True),
        ("FS-006", "Accumulated depreciation is a?", "contra_asset", True),
        ("FS-007", "Candidate says land is always depreciated under IAS 16.", "false", False),
        ("FS-008", "Treasury stock reduces?", "equity", True),
        ("FS-009", "Gross profit equals sales minus?", "cogs", True),
        ("FS-010", "Operating income is after interest expense?", "no", True),
    ]
    for cid, q, ans, ok in fs_items:
        cand = ans if ok else ("true" if ans == "false" else "asset")
        if cid == "FS-007":
            cand = "true"
        add(
            _case(
                case_id=cid,
                category="financial_statements",
                difficulty="easy",
                question=f"{q} Single token/label.",
                expected_answer=ans,
                structured_golden=GoldenAnswer(mode=GradeMode.EXACT_TEXT, value=ans),
                grading_rubric=_rubric("Correct statement/element classification.", "Misstated element."),
                known_failure_modes=[F.FIN_ACC_002.value, F.FIN_HALL_006.value],
                tags=["statements"],
                candidate_response=cand,
                planted_failure=F.FIN_HALL_006.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- Audit / controls / recon / anomaly (20) ---
    audit_items = [
        ("AUD-001", "Management refuses inventory count observation. Risk mainly affects?", "existence", True, F.FIN_NONE),
        ("AUD-002", "Unsupported conclusion: 'fraud proven' from one late invoice?", "unsupported", False, F.FIN_AUD_004),
        ("AUD-003", "Bank confirmations primarily test cash?", "existence", True, F.FIN_NONE),
        ("AUD-004", "Going concern doubt requires only verbal management optimism as evidence?", "no", True, F.FIN_NONE),
        ("AUD-005", "Material misstatement risk rises when controls are weak?", "yes", True, F.FIN_NONE),
        ("CTRL-001", "Segregation of duties: same person records and custodians cash — weakness?", "yes", True, F.FIN_NONE),
        ("CTRL-002", "Password sharing improves control efficiency?", "no", True, F.FIN_NONE),
        ("CTRL-003", "Candidate claims approvals are unnecessary if ERP auto-posts.", "false", False, F.FIN_CTRL_012),
        ("CTRL-004", "Three-way match typically links PO, receipt, and?", "invoice", True, F.FIN_NONE),
        ("CTRL-005", "Mandatory vacation can help detect fraud?", "yes", True, F.FIN_NONE),
        ("REC-001", "Book cash 10,000; bank 9,700; outstanding checks 400; deposit in transit 100. Reconciled cash?", "9700", False, F.FIN_RECON_013),
        ("REC-002", "Book 8,500; bank 8,200; outstanding checks 500; DIT 200. Reconciled?", "8200", True, F.FIN_NONE),
        ("REC-003", "Book 5,000; NSF check 100 not yet recorded. Adjusted book before reconciling items?", "4900", True, F.FIN_NONE),
        ("REC-004", "Bank error overstated deposit by 50; bank shows 3,050 true deposit 3,000. Adjust bank?", "3000", True, F.FIN_NONE),
        ("REC-005", "Outstanding checks should be added to bank balance?", "no", True, F.FIN_NONE),
        ("ANOM-001", "Weekend vendor payments spike 10x with new payee — flag?", "yes", True, F.FIN_NONE),
        ("ANOM-002", "Round-dollar invoices just below approval threshold repeatedly — flag?", "yes", True, F.FIN_NONE),
        ("ANOM-003", "Seasonal sales rise 5% YoY alone proves fraud?", "no", True, F.FIN_NONE),
        ("ANOM-004", "Candidate invents a 'GAAP weekend payment ban' as the reason.", "hallucination", False, F.FIN_HALL_006),
        ("ANOM-005", "Duplicate invoice numbers to same vendor same day — flag?", "yes", True, F.FIN_NONE),
    ]
    # Fix REC-001 expected: bank + DIT - outstanding = 9700 + 100 - 400 = 9400
    recon_fix = {
        "REC-001": ("9400", "9700"),  # expected, candidate wrong
        "REC-002": ("8200", "8200"),  # 8200+200-500=7900 wait recalculate
    }
    # REC-002: bank 8200 + DIT 200 - OC 500 = 7900
    for cid, q, ans, ok, fail in audit_items:
        if cid == "REC-001":
            ans, cand = "9400", "9700"
            ok = False
            fail = F.FIN_RECON_013
        elif cid == "REC-002":
            ans, cand = "7900", "7900"
            ok = True
            fail = F.FIN_NONE
        else:
            cand = ans if ok else ("yes" if ans == "no" else "supported" if ans == "unsupported" else "true")
            if cid == "AUD-002":
                cand = "fraud_proven"
            if cid == "CTRL-003":
                cand = "true"
            if cid == "ANOM-004":
                cand = "gaap_weekend_ban"
        cat = (
            "audit_reasoning"
            if cid.startswith("AUD")
            else "internal_controls"
            if cid.startswith("CTRL")
            else "reconciliation"
            if cid.startswith("REC")
            else "anomaly_detection"
        )
        mode = GradeMode.NUMERIC if cid.startswith("REC") and ans.isdigit() else GradeMode.EXACT_TEXT
        gold = (
            GoldenAnswer(mode=GradeMode.NUMERIC, value=float(ans), tolerance=0.5)
            if mode == GradeMode.NUMERIC
            else GoldenAnswer(mode=GradeMode.EXACT_TEXT, value=ans)
        )
        add(
            _case(
                case_id=cid,
                category=cat,  # type: ignore[arg-type]
                difficulty="medium",
                question=f"{q} Concise answer.",
                expected_answer=ans,
                structured_golden=gold,
                grading_rubric=_rubric("Domain-correct concise answer.", "Unsupported or wrong control/audit claim."),
                known_failure_modes=[fail.value],
                tags=[cat],
                candidate_response=str(cand),
                planted_failure=fail.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- Financial analysis narrative evidence (8) ---
    for i in range(1, 9):
        need = ["REV-note-12", "AR-aging"]
        ok = i % 3 != 0
        cand = (
            "Margin compression driven by COGS; supported by REV-note-12 and AR-aging."
            if ok
            else "Company will definitely beat guidance next quarter with no cited evidence."
        )
        add(
            _case(
                case_id=f"FA-{i:03d}",
                category="financial_analysis",
                difficulty="hard",
                question=(
                    "Using only provided evidence IDs, state whether margin compression is "
                    f"supported and cite required evidence IDs: {', '.join(need)}. "
                    "Include both evidence IDs if supported."
                ),
                expected_answer="supported; REV-note-12; AR-aging",
                structured_golden=GoldenAnswer(
                    mode=GradeMode.CONTAINS_ALL, value=need if ok else need
                ),
                grading_rubric=_rubric(
                    "Cites all required evidence IDs; no unsupported forecast.",
                    "Missing citations or hallucinated certainty.",
                ),
                required_evidence=need,
                known_failure_modes=[F.FIN_EVID_009.value, F.FIN_HALL_006.value],
                tags=["analysis", "evidence"],
                candidate_response=cand,
                planted_failure=F.FIN_EVID_009.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- SQL financial (16) ---
    sql_cases = [
        ("SQL-001", "Total revenue from sales table", "SELECT SUM(amount) AS total_revenue FROM sales;", 15000.0, True),
        ("SQL-002", "Count distinct customers", "SELECT COUNT(DISTINCT customer_id) AS n FROM sales;", 42.0, True),
        ("SQL-003", "Average order value", "SELECT AVG(amount) AS aov FROM sales;", 250.5, True),
        ("SQL-004", "Expenses by category total for COGS", "SELECT SUM(amount) FROM expenses WHERE category='COGS';", 8000.0, True),
        ("SQL-005", "Monthly revenue for 2024-01", "SELECT SUM(amount) FROM sales WHERE month='2024-01';", 3200.0, True),
        ("SQL-006", "Top vendor spend", "SELECT vendor, SUM(amount) s FROM ap GROUP BY vendor ORDER BY s DESC LIMIT 1;", 9100.0, True),
        ("SQL-007", "AR open balance", "SELECT SUM(balance) FROM ar WHERE status='open';", 18750.0, True),
        ("SQL-008", "Cash receipts March", "SELECT SUM(amount) FROM cash_receipts WHERE month='2024-03';", 5400.0, True),
        ("SQL-009", "Gross margin dollars", "SELECT SUM(sales)-SUM(cogs) FROM monthly_gm;", 12000.0, True),
        ("SQL-010", "Payroll expense total", "SELECT SUM(amount) FROM expenses WHERE category='payroll';", 22000.0, True),
        ("SQL-011", "Wrong: average of sums as total revenue", "SELECT AVG(amount) FROM sales;", 15000.0, False),
        ("SQL-012", "Wrong join double counts", "SELECT SUM(s.amount) FROM sales s JOIN returns r ON s.id=r.sale_id;", 14000.0, False),
        ("SQL-013", "Inventory on hand units", "SELECT SUM(qty) FROM inventory;", 1300.0, True),
        ("SQL-014", "Late invoices count >30 days", "SELECT COUNT(*) FROM ar WHERE days_outstanding>30;", 17.0, True),
        ("SQL-015", "Capex cash outflows", "SELECT SUM(amount) FROM cash_flows WHERE section='investing' AND amount<0;", -45000.0, True),
        ("SQL-016", "Instruction fail: prose instead of SQL", "SELECT 1;", 1.0, False),
    ]
    for cid, title, sql, result, ok in sql_cases:
        if cid == "SQL-011":
            cand = "250.5"  # avg instead of sum
            fail = F.FIN_SQL_007
        elif cid == "SQL-012":
            cand = "28000"  # double count
            fail = F.FIN_SQL_007
        elif cid == "SQL-016":
            cand = "Just add up the sales numbers in Excel."
            fail = F.FIN_INST_014
        else:
            cand = str(int(result) if result == int(result) else result)
            fail = F.FIN_NONE
        add(
            _case(
                case_id=cid,
                category="sql_financial",
                difficulty="medium",
                question=(
                    f"{title}. Given the fixture result for canonical SQL:\n{sql}\n"
                    "Return the numeric query result only (offline graded against golden result)."
                ),
                expected_answer=str(result),
                structured_golden=GoldenAnswer(
                    mode=GradeMode.SQL_RESULT,
                    value={"sql": sql, "result": result},
                    tolerance=0.01,
                ),
                grading_rubric=_rubric(
                    "Numeric result matches golden fixture within 0.01.",
                    "Wrong aggregation/join or non-numeric answer.",
                ),
                allowed_tolerance=0.01,
                required_evidence=["sql_fixture"],
                known_failure_modes=[F.FIN_SQL_007.value, F.FIN_INST_014.value],
                tags=["sql"],
                candidate_response=cand,
                planted_failure=fail.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- Python financial (16) ---
    py_cases = [
        ("PY-001", "def gm(s,c): return (s-c)/s", (100, 60), 0.4, True),
        ("PY-002", "compound: 1000*((1+0.05)**3)", None, 1157.625, True),
        ("PY-003", "NPV: -1000 + 600/1.1 + 600/1.1**2", None, 41.3223, True),
        ("PY-004", "straight-line dep: (cost-salvage)/life = (10000-1000)/5", None, 1800.0, True),
        ("PY-005", "contribution margin: price-variable = 50-30", None, 20.0, True),
        ("PY-006", "break-even units: fixed/(price-var)=10000/20", None, 500.0, True),
        ("PY-007", "ROI: (gain-cost)/cost = (120-100)/100", None, 0.2, True),
        ("PY-008", "working capital: CA-CL = 80-50", None, 30.0, True),
        ("PY-009", "simple interest: p*r*t = 2000*0.06*2", None, 240.0, True),
        ("PY-010", "cagr approx: (1200/1000)**(1/2)-1", None, 0.0954, True),
        ("PY-011", "planted wrong compound interest", None, 1157.625, False),
        ("PY-012", "gross profit dollars sales-cogs 500-320", None, 180.0, True),
        ("PY-013", "debt ratio liabilities/assets 40/100", None, 0.4, True),
        ("PY-014", "payback years 1000 CF annual 250", None, 4.0, True),
        ("PY-015", "planted: uses revenue as cash always", None, 1.0, False),
        ("PY-016", "margin of safety (sales-BE)/sales (1000-500)/1000", None, 0.5, True),
    ]
    for cid, title, _args, result, ok in py_cases:
        if cid == "PY-011":
            cand = "1150"  # wrong compound
            fail = F.FIN_PY_008
        elif cid == "PY-015":
            cand = "1"  # nonsense
            fail = F.FIN_CF_003
        else:
            cand = f"{result:.4f}" if isinstance(result, float) and result != int(result) else str(result)
            fail = F.FIN_NONE
        add(
            _case(
                case_id=cid,
                category="python_financial",
                difficulty="medium",
                question=(
                    f"Compute the financial result for: {title}. "
                    "Return a number only. Offline graded vs golden numeric result."
                ),
                expected_answer=str(result),
                structured_golden=GoldenAnswer(
                    mode=GradeMode.PYTHON_RESULT,
                    value={"expression": title, "result": float(result)},
                    tolerance=0.02,
                ),
                grading_rubric=_rubric(
                    "Numeric result within tolerance.",
                    "Incorrect financial calculation.",
                ),
                allowed_tolerance=0.02,
                known_failure_modes=[F.FIN_PY_008.value, F.FIN_CALC_001.value],
                tags=["python"],
                candidate_response=cand,
                planted_failure=fail.value if not ok else F.FIN_NONE.value,
            )
        )

    # --- Extra statement / analysis fillers to reach ~150 ---
    for i in range(1, 11):
        sales = 10_000 * i
        opex = 3_000 * i
        ebit = sales - opex
        ok = i % 4 != 0
        cand = str(ebit if ok else ebit + 500)
        add(
            _case(
                case_id=f"ANL-{i:03d}",
                category="financial_analysis",
                difficulty="easy",
                question=f"Sales {sales}, operating expenses {opex}. Operating income? Number only.",
                expected_answer=str(ebit),
                structured_golden=GoldenAnswer(mode=GradeMode.NUMERIC, value=float(ebit), tolerance=0.01),
                grading_rubric=_rubric("Sales minus operating expenses.", "Arithmetic error."),
                known_failure_modes=[F.FIN_CALC_001.value],
                tags=["analysis", "ebit"],
                candidate_response=cand,
                planted_failure=F.FIN_CALC_001.value if not ok else F.FIN_NONE.value,
            )
        )

    # Instruction-following format traps (6)
    for i in range(1, 7):
        ok = i % 2 == 1
        add(
            _case(
                case_id=f"INST-{i:03d}",
                category="financial_ratios",
                difficulty="easy",
                question="Compute 2+2 for a control check. Reply with ONLY the digit.",
                expected_answer="4",
                structured_golden=GoldenAnswer(mode=GradeMode.EXACT_TEXT, value="4"),
                grading_rubric=_rubric("Exactly '4'.", "Any extra words."),
                known_failure_modes=[F.FIN_INST_014.value],
                tags=["instruction"],
                candidate_response="4" if ok else "The answer is 4.",
                planted_failure=F.FIN_NONE.value if ok else F.FIN_INST_014.value,
            )
        )

    return cases


def write_dataset() -> dict:
    cases = build_cases()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for case in cases:
        lines.append(case.model_dump_json())
    text = "\n".join(lines) + "\n"
    OUT.write_bytes(text.encode("utf-8"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    by_cat: dict[str, int] = {}
    planted = 0
    for c in cases:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
        if c.planted_failure != F.FIN_NONE.value:
            planted += 1
    manifest = {
        "dataset_version": DATASET_VERSION,
        "n_cases": len(cases),
        "sha256": digest,
        "path": str(OUT.relative_to(ROOT.parent)).replace("\\", "/"),
        "categories": by_cat,
        "planted_failures": planted,
        "license_note": "Original synthetic items; not copied from copyrighted exams.",
    }
    MANIFEST.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    return manifest


if __name__ == "__main__":
    m = write_dataset()
    print(json.dumps(m, indent=2))

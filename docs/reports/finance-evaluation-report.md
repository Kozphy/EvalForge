# Finance + Accounting LLM Evaluation Report

**Dataset:** `finance-accounting-v1` · **Prompt version:** `finance-eval-prompt-v1`  
**Run ID:** `finrun_2f228ff6366e` · **Model:** `offline-candidate-fixture` `v1`  
**Policy decision:** `FAIL` · **Human review status:** `SEEDED_PARTIAL`

## Executive Summary

Financial AI systems can produce fluent answers that are materially wrong (misstated equity, unbalanced journals, cash/profit confusion, fabricated standards). This report evaluates a reproducible offline candidate against a versioned golden set using deterministic grading as the source of truth, with simulated judge scores and seeded human reviews for disagreement measurement.

- Cases evaluated: **154**
- Accuracy / pass rate: **79.9%** (95% bootstrap CI [0.7402597402597403, 0.8571428571428571])
- Hallucination rate (FIN-HALL-006): **0.6%**
- Critical error rate: **5.2%**
- Calculation error rate: **5.2%**
- Policy: **FAIL** — FAIL. FIN-POL-001: critical_error_rate > 0.05 → FAIL; FIN-POL-004: critical regression on critical_error_rate → FAIL

## Research Questions

1. Can deterministic graders detect material finance/accounting errors without an LLM judge?
2. Which failure classes dominate under a planted-error offline candidate?
3. Do policy gates block release when critical financial error rates exceed thresholds?
4. How often do simulated judge decisions disagree with seeded human reviews?

## Dataset

- Version: `finance-accounting-v1`
- SHA256: `d6d2ede08b0ca6eecd040c3e6e54ba4337e7cae14e67ec196c8fb4d008a4c80f`
- Size: 154 original synthetic items (not copyrighted exam reproductions)
- Categories: financial statements, journals, equations, revenue, expenses, margins, cash flow, ratios, audit, controls, reconciliation, anomalies, analysis, SQL, Python

## Evaluation Methodology

```text
Input → Candidate Response → Parser → Deterministic Metrics
     → Simulated Judge Rubric → Seeded Human Review
     → Failure Taxonomy → Baseline Regression → Policy Gate → Audit Evidence
```

- **Deterministic-first:** numeric, exact text, journal JSON, SQL/Python result fixtures
- **LLM-as-judge:** not required for this report; scores are labeled `simulated_heuristic_judge`
- **Human review:** curated seed on a subset; disagreement tracked when present

## Metrics

```json
{
  "n_cases": 154,
  "n_passed": 123,
  "accuracy": 0.7987012987012987,
  "pass_rate": 0.7987012987012987,
  "hallucination_rate": 0.006493506493506494,
  "calculation_error_rate": 0.05194805194805195,
  "reasoning_error_rate": 0.045454545454545456,
  "citation_evidence_failure_rate": 0.012987012987012988,
  "instruction_following_failure_rate": 0.025974025974025976,
  "critical_error_rate": 0.05194805194805195,
  "mean_latency_ms": null,
  "total_tokens": null,
  "estimated_cost_usd": null,
  "precision": 1.0,
  "recall": 1.0,
  "f1": 1.0,
  "false_positive_rate": 0.0,
  "accuracy_ci95": [
    0.7402597402597403,
    0.8571428571428571
  ],
  "failure_counts": {
    "FIN-NONE": 123,
    "FIN-CALC-001": 7,
    "FIN-JE-011": 1,
    "FIN-ACC-002": 5,
    "FIN-REV-010": 4,
    "FIN-CF-003": 1,
    "FIN-AUD-004": 1,
    "FIN-CTRL-012": 1,
    "FIN-RECON-013": 1,
    "FIN-HALL-006": 1,
    "FIN-EVID-009": 2,
    "FIN-SQL-007": 2,
    "FIN-INST-014": 4,
    "FIN-PY-008": 1
  }
}
```

## Results

Passed 123 / 154. Latency/cost are null for the offline fixture candidate (no live model calls).

## Failure Analysis

| Code | Name | Count |
|---|---|---:|
| `FIN-CALC-001` | arithmetic_error | 7 |
| `FIN-ACC-002` | accounting_classification_error | 5 |
| `FIN-REV-010` | revenue_recognition_error | 4 |
| `FIN-INST-014` | instruction_following_failure | 4 |
| `FIN-EVID-009` | unsupported_by_evidence | 2 |
| `FIN-SQL-007` | incorrect_sql_aggregation_or_join | 2 |
| `FIN-JE-011` | journal_entry_error | 1 |
| `FIN-CF-003` | cash_flow_profit_confusion | 1 |

## Ablation / Comparison

Baseline comparison:

```json
{
  "regressions": [
    {
      "metric": "accuracy",
      "baseline": 1.0,
      "candidate": 0.7987012987012987,
      "delta": -0.2012987012987013,
      "severity": "high"
    },
    {
      "metric": "critical_error_rate",
      "baseline": 0.0,
      "candidate": 0.05194805194805195,
      "delta": 0.05194805194805195,
      "severity": "critical"
    }
  ],
  "new_failure_categories": [
    "FIN-ACC-002",
    "FIN-AUD-004",
    "FIN-CALC-001",
    "FIN-CF-003",
    "FIN-CTRL-012",
    "FIN-EVID-009",
    "FIN-HALL-006",
    "FIN-INST-014",
    "FIN-JE-011",
    "FIN-PY-008",
    "FIN-RECON-013",
    "FIN-REV-010",
    "FIN-SQL-007"
  ],
  "accuracy_delta": -0.2012987012987013
}
```

## Human-vs-Judge Agreement

- Seeded human reviews: **20**
- Agreement rate (decision): **0.95**

Agreement is measured only on the seeded subset. Do not extrapolate to production.

## Cost and Latency

- Offline fixture run: no token usage, no API cost.
- Live model hooks can populate `latency_ms`, token counts, and `estimated_cost_usd` per case.

## Threats to Validity

- Candidate responses are embedded fixtures with planted errors (not a blind live model).
- Judge is simulated from deterministic outcomes (not independent).
- SQL/Python grading checks numeric results, not sandboxed execution of arbitrary code.
- Human reviews are curated seeds for pipeline demonstration.

## Limitations

- Not production financial advice or audit assurance.
- Golden set is small (~100–200) and synthetic.
- No claim of GAAP/IFRS certification coverage.

## Governance Implications

- Critical accounting and hallucination rates can force **FAIL** or **HUMAN_REVIEW_REQUIRED**.
- Evidence manifests include dataset hash, metrics, failure classes, and policy decision.
- Deterministic checks remain authoritative over fluent LLM rationales.

## Reproduction Instructions

```bash
python -m finance_eval generate-dataset
python -m finance_eval run --write-baseline
python -m finance_eval report
pytest tests/test_finance_eval.py -q
```

## Maturity Labels

| Component | Label |
|---|---|
| Dataset | implemented |
| Deterministic grading | implemented |
| LLM judge | simulated |
| Human review seed | curated_seed |
| Policy gate | implemented |
| Evidence JSON/JSONL | implemented (file append) |
| Production adoption | not claimed |

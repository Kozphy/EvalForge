# EvalForge AI Release Audit — Commercial Pilot

## Customer promise

Before an AI, RAG, or agent release reaches production, EvalForge compares a baseline run with a candidate run and produces a deterministic **PASS / FAIL** decision with case-level regression evidence.

## Pilot deliverable

A pilot engagement should include:

1. 50–300 representative customer cases.
2. A frozen baseline run.
3. A candidate run using the proposed model/prompt/RAG configuration.
4. A release-gate policy agreed before evaluation.
5. A comparison report covering quality, major regressions, human-review load, and API failures.
6. A prioritized list of failed cases for remediation.
7. A rerun after one remediation cycle.

## Default release policy

The initial conservative policy is:

- candidate accuracy must not decline;
- zero new major case regressions;
- zero additional human-review cases;
- zero additional API errors.

Customers can explicitly relax thresholds when their risk appetite differs.

## API contract target

`GET /api/runs/{baseline_run_id}/compare/{candidate_run_id}` should return:

```json
{
  "decision": "PASS",
  "baseline_run_id": 10,
  "candidate_run_id": 11,
  "summary": {
    "shared_case_count": 200,
    "baseline_accuracy": 0.84,
    "candidate_accuracy": 0.89,
    "accuracy_delta": 0.05,
    "regression_count": 0,
    "major_regression_count": 0,
    "improvement_count": 18
  },
  "regressions": [],
  "reasons": [],
  "policy": {}
}
```

## What is sellable now vs later

### Pilot-ready after merge

- private/single-customer deployment;
- benchmark import;
- repeatable evaluation runs;
- baseline vs candidate release decision;
- regression evidence;
- existing JSON/JSONL/CSV run exports;
- human-review workflow.

### Required before public SaaS

- authentication;
- tenant isolation;
- RBAC;
- API-key management;
- rate limiting;
- outbound-network/SSRF controls;
- PostgreSQL and migration discipline;
- background workers;
- usage metering and billing;
- security review and operational monitoring.

## Sales positioning

Do not sell "an LLM evaluation framework." Sell a release decision:

> We test your AI change against your own benchmark and tell you which cases regressed before you deploy it.

A finance/accounting/compliance specialization is especially suitable because EvalForge already supports evidence-grounded checks and human adjudication.

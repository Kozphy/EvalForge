# EvalForge AI Release Audit — Commercial Pilot

## Customer promise

Before an AI, RAG, or agent release reaches production, EvalForge compares a frozen baseline run with a candidate run on the **same benchmark** and produces a deterministic **PASS / FAIL** decision with case-level regression evidence.

This is a release-quality assessment, not a guarantee that an AI system is safe, correct, compliant, or suitable for production. High-risk deployments still require domain review, security controls, and human approval.

## Pilot deliverable

A pilot engagement should include:

1. 50–300 representative customer cases with stable case IDs.
2. Human-reviewed expected labels when accuracy is part of the release policy.
3. A frozen baseline run.
4. A candidate run using the proposed model, prompt, retrieval, or agent configuration.
5. A release-gate policy agreed **before** evaluation.
6. A comparison report covering benchmark coverage, quality delta, case regressions, human-review load, and API failures.
7. A prioritized list of failed cases for remediation.
8. One rerun after a remediation cycle.

## Default release policy

The default policy is intentionally conservative:

- baseline and candidate must belong to the same project;
- both runs must be completed;
- the two runs must contain the same benchmark case set;
- both runs must contain labeled accuracy metrics;
- candidate accuracy must not decline;
- zero new major case regressions;
- zero additional human-review cases;
- zero additional API errors.

Thresholds may be explicitly changed before a run when a customer's documented risk policy differs. A customer should not relax thresholds after seeing the candidate result simply to convert a FAIL into a PASS.

## Release decision output

`app.release_gate.compare_runs()` currently returns a structured decision object. A representative result is:

```json
{
  "decision": "PASS",
  "baseline_run_id": 10,
  "candidate_run_id": 11,
  "summary": {
    "baseline_case_count": 200,
    "candidate_case_count": 200,
    "shared_case_count": 200,
    "missing_from_candidate_count": 0,
    "new_in_candidate_count": 0,
    "baseline_accuracy": 0.84,
    "candidate_accuracy": 0.89,
    "accuracy_delta": 0.05,
    "regression_count": 0,
    "major_regression_count": 0,
    "improvement_count": 18,
    "baseline_human_review_count": 12,
    "candidate_human_review_count": 9,
    "human_review_delta": -3,
    "baseline_api_error_count": 1,
    "candidate_api_error_count": 0,
    "api_error_delta": -1
  },
  "regressions": [],
  "reasons": [],
  "policy": {
    "min_accuracy_delta": 0.0,
    "max_major_regressions": 0,
    "max_new_review_cases": 0,
    "max_api_error_delta": 0,
    "require_same_case_set": true,
    "require_labeled_accuracy": true
  }
}
```

## Important failure conditions

EvalForge refuses to produce the default release decision when comparison integrity is weak. Examples include:

- baseline and candidate are from different projects;
- either run is incomplete;
- the runs have no comparable cases;
- the candidate silently dropped or added benchmark cases;
- labeled accuracy is missing under the default policy;
- duplicate case comparison keys are present;
- an unsupported severity value is encountered.

These conditions are treated as invalid comparisons rather than silently converted to zero-valued metrics.

## Customer-facing report format

A commercial report should contain:

### 1. Release decision

**Decision:** PASS / FAIL  
**Baseline:** run ID + model/config snapshot  
**Candidate:** run ID + model/config snapshot  
**Benchmark:** dataset version + case count  
**Policy:** thresholds frozen before execution

### 2. Executive summary

| Measure | Baseline | Candidate | Delta | Gate |
|---|---:|---:|---:|---|
| Accuracy | 0.84 | 0.89 | +0.05 | PASS |
| Major regressions | — | 0 | 0 | PASS |
| Human review cases | 12 | 9 | -3 | PASS |
| API errors | 1 | 0 | -1 | PASS |

### 3. Regression evidence

For every regressed case include the case ID/name, baseline severity, candidate severity, candidate reason, and enough evidence for a reviewer to reproduce the decision.

### 4. Limitations

State benchmark scope, labeling limitations, grader limitations, known retrieval limitations, security assumptions, and any customer-specific policy exceptions.

### 5. Recommended action

- **PASS:** eligible to proceed to the customer's remaining release controls.
- **FAIL:** remediate listed regressions, rerun the same benchmark, and retain both reports for auditability.

## API status

The comparison engine is implemented in `app/release_gate.py`. A public FastAPI comparison endpoint and downloadable HTML/PDF release report are **not part of this PR** and should be implemented as the next productization step. This document intentionally does not claim those interfaces already exist.

## What is sellable now vs later

### Pilot-ready after this PR is merged and tests are green

- private/single-customer deployment;
- benchmark import;
- repeatable evaluation runs;
- programmatic baseline-vs-candidate release decision;
- case-level regression evidence;
- existing JSON/JSONL/CSV run exports;
- human-review workflow;
- documented pilot/report methodology.

### Required before public multi-tenant SaaS

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

Do not sell "an LLM evaluation framework." Sell a controlled release decision:

> We test your AI change against your own frozen benchmark, identify what regressed, and give your team evidence for the release decision before deployment.

A finance, accounting, or compliance specialization is especially suitable because EvalForge already supports evidence-grounded checks and human adjudication.

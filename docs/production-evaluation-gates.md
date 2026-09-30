# Production Evaluation & Release Gates

EvalForge v0.4 upgrades evaluation from a reporting workflow into a release-control workflow.

## Target pipeline

```text
Dataset / Golden Set
        ↓
Evaluation Runner
        ↓
Deterministic metrics
+ LLM-as-Judge
+ Human evaluation
        ↓
Statistical significance
+ confidence intervals
        ↓
Quality / Safety / Cost / Latency
        ↓
Baseline comparison
        ↓
Regression detection
        ↓
Policy Gate
        ↓
GitHub PR
        ↓
PASS → merge
FAIL → block + RCA
```

## What is implemented in this upgrade

- Deterministic release policy engine with fail-closed required metrics.
- Absolute minimum/maximum thresholds.
- Baseline regression budgets.
- Zero-tolerance severe safety failure gate by default.
- Bootstrap confidence intervals.
- Paired bootstrap candidate-vs-baseline comparison.
- CI-compatible command that exits non-zero on gate failure.
- GitHub Actions enforcement example.
- Quality, safety, p95 latency, and per-case cost policy dimensions.

## Golden-set contract

A production golden set should be immutable for a released benchmark version. Every case should carry:

- stable case ID;
- benchmark/dataset version;
- input/prompt;
- expected output or expected label where applicable;
- deterministic requirements;
- approved evidence IDs for grounded tasks;
- safety/risk tags;
- human gold label and adjudication status where applicable.

Never silently mutate a released golden set. Publish a new version and preserve the previous benchmark for reproducibility.

## Statistical policy

Use confidence intervals to describe uncertainty, not to manufacture certainty. When candidate and baseline are evaluated on the same cases, prefer paired comparisons because case difficulty is shared.

A release should normally satisfy both:

1. absolute product thresholds; and
2. regression constraints against the last approved baseline.

For high-risk systems, policy may additionally require the lower confidence bound to exceed a minimum threshold and human adjudication for safety-critical slices.

## Gate input contract

Candidate and baseline artifacts use this shape:

```json
{
  "metrics": {
    "quality_score": 0.91,
    "safety_score": 0.99,
    "latency_p95_ms": 1800.0,
    "cost_per_case_usd": 0.021
  },
  "safety_failures": 0
}
```

The default policy is in `config/release_policy.json`.

## Local usage

```bash
python scripts/ci_eval_gate.py \
  --candidate examples/ci_candidate.json \
  --baseline examples/ci_baseline.json \
  --policy config/release_policy.json \
  --output gate-report.json
```

Exit code `0` means PASS. Exit code `1` means FAIL and should block the PR.

## RCA contract after failure

A failed gate should emit machine-readable violation codes. The next automation layer can map those codes into root-cause workflows:

- `MISSING_REQUIRED_METRIC` → telemetry/evaluation pipeline defect;
- `BELOW_MINIMUM` → product quality failure;
- `ABOVE_MAXIMUM` → latency/cost budget failure;
- `REGRESSION_EXCEEDED` → baseline regression investigation;
- `SAFETY_FAILURES_EXCEEDED` → safety incident review and mandatory human escalation.

This is the integration point for a CI repair/orchestration system. EvalForge decides whether AI behavior is releasable; the orchestrator decides how engineering failures are diagnosed and repaired.

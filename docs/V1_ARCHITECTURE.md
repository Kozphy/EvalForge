# EvalForge v1 — Production Evaluation Architecture

EvalForge v1 evolves the local evaluation workbench into an **LLMOps / Agent Evaluation Infrastructure** layer while preserving the local-first and human-adjudication principles.

## Target control loop

```text
Dataset Registry
      ↓
Immutable Dataset Version
      ↓
Benchmark / Agent Runner
      ↓
Deterministic Graders ──→ Evidence Retrieval
      ↓                         ↓
Optional LLM Judge ←────────────┘
      ↓
Human Gold Labels / Adjudication
      ↓
Calibration + Metrics
      ↓
Baseline Comparison
      ↓
Regression / Policy Gate
      ↓
PASS ─────────────── BLOCK / HUMAN REVIEW
      ↓
Canary Evaluation
      ↓
Production Evidence + Audit Trail
```

## v1 capability map

| Capability | Purpose | Exit criterion |
|---|---|---|
| Dataset versioning | Make benchmarks reproducible | Every run pins an immutable dataset fingerprint |
| Benchmark registry | Separate named benchmark suites from ad-hoc cases | Benchmark ID/version appears in run evidence |
| Baselines | Compare candidate vs known-good run | Delta metrics generated automatically |
| Regression gates | Prevent degraded models/agents from shipping | Configurable thresholds return pass/block/review |
| Cost/latency telemetry | Evaluate quality-efficiency tradeoffs | p50/p95 latency, tokens and estimated cost per run |
| Calibration | Measure judge confidence against gold labels | Calibration/error report available per grader |
| CI evaluation | Make evaluation continuous testing | CLI/API returns machine-readable gate result |
| Canary evaluation | Validate candidate on controlled production slice | Candidate can be promoted or rolled back by policy |
| Audit evidence | Explain what ran and why it passed | Hash-linked evidence manifest for every gated run |
| Observability | Operate the evaluation service | Structured logs, traces and run-level SLO metrics |

## Policy gate contract

A gate should never be only `accuracy >= X`. v1 evaluates multiple dimensions:

- quality: accuracy/F1 and task-specific metrics
- safety/control: critical deterministic findings must be zero unless explicitly waived
- regression: candidate delta against a pinned baseline
- reliability: API/error rate and incomplete-case rate
- performance: latency budgets
- economics: token/cost budgets when provider usage is measurable
- uncertainty: disagreement and human-review rate

Gate outcomes:

- `PASS` — all mandatory policies satisfied
- `BLOCK` — hard regression or control violation
- `REVIEW` — uncertainty, missing evidence, or explicitly reviewable threshold breach

## Production-proof evidence

A release claim should point to artifacts rather than prose. A v1 proof bundle should contain:

1. dataset + benchmark version/fingerprint
2. application and Git SHA
3. grader configuration snapshot
4. candidate and baseline metrics
5. regression deltas
6. latency/cost/error telemetry
7. policy decision and reasons
8. human adjudication records where required
9. machine-readable report suitable for CI

## Delivery phases

### Phase 1 — reproducibility and regression

Dataset versions, benchmark registry, baseline run selection, metric deltas and policy-gate API/CLI.

### Phase 2 — telemetry and CI

Token/cost/latency aggregation, structured run telemetry, CI workflow and downloadable evidence manifest.

### Phase 3 — evaluation science

Human gold sets, inter-annotator agreement, judge calibration, ablations, failure taxonomy and statistical confidence intervals.

### Phase 4 — production operation

Async workers, PostgreSQL, RBAC/multi-tenancy, rate limits, tracing, SLOs, canary evaluation and rollback/promotion policy.

## Non-goals

EvalForge does not become a truth oracle. LLM judges remain fallible; unsupported claims remain distinct from false claims; high-risk or uncertain outcomes remain eligible for human adjudication.

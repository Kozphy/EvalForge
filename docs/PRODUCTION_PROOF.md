# Production Proof

Use this checklist before describing an EvalForge-backed system as production-proven.

## Reproducibility
- [ ] Benchmark dataset is versioned and fingerprinted.
- [ ] Run records Git SHA, application version, model/provider and grader config.
- [ ] Baseline run is explicitly pinned.
- [ ] A clean environment can reproduce the benchmark.

## Evaluation evidence
- [ ] Candidate and baseline run the same benchmark version.
- [ ] Accuracy/F1 and task-specific metrics are reported.
- [ ] Failure taxonomy is reported, not only aggregate score.
- [ ] Human-reviewed gold labels exist for a representative subset.
- [ ] Judge disagreement/calibration is measured where an LLM judge is used.

## Reliability
- [ ] API error and incomplete-case rates are measured.
- [ ] Failure injection covers timeouts, malformed output, provider errors and missing evidence.
- [ ] Retry behavior has a bounded budget and stopping condition.

## Performance and economics
- [ ] p50/p95 latency is recorded.
- [ ] Token usage and estimated cost are recorded when available.
- [ ] Quality/cost and quality/latency tradeoffs are visible.

## Delivery controls
- [ ] CI executes the benchmark or an explicitly documented representative subset.
- [ ] Regression policy produces PASS/BLOCK/REVIEW.
- [ ] Failed mandatory gates block release.
- [ ] Human approval is required for configured high-risk outcomes.

## Operations
- [ ] Structured logs/traces identify project, benchmark, dataset and run.
- [ ] SLOs and alert thresholds are documented.
- [ ] Canary policy and rollback criteria are documented and exercised.
- [ ] Production evidence is retained as a machine-readable artifact.

A screenshot or successful demo is **not** production proof by itself. Production proof is reproducible evidence that the system meets declared quality, reliability, performance, economic and governance constraints.

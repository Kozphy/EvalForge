# EvalForge Research Plan

## Working title

**EvalForge: Reliable Evaluation of AI-Generated Responses with Deterministic Rules, Evidence Grounding, and Human Review**

## Motivation

LLM-as-a-judge evaluation is convenient, but it can be unstable, opaque, and hard to audit. EvalForge studies whether a hybrid pipeline evaluates more reliably than simpler alternatives. The pipeline combines deterministic checks, approved-evidence retrieval, a structured judge, uncertainty controls, and human-review routing.

## Research questions (canonical)

**RQ1.** Does a hybrid evaluation pipeline combining deterministic rules, evidence retrieval, structured LLM judging, and human-review routing detect AI-output failures more reliably than simpler evaluation approaches?

**RQ2.** Which components of the hybrid evaluator contribute most to accuracy, false-positive reduction, and review efficiency?

The earlier draft had four questions; they map onto these two. Detection quality and false positives fall under RQ1. Component contribution and operational trade-offs fall under RQ2.

## Systems (identical frozen cases for all)

| ID | System | Components |
|---|---|---|
| B1 | Deterministic-only | `check_rules`; any failed rule → fail |
| B2 | Single judge | one judge call; no evidence, no rules, no routing |
| B3 | Grounded judge | approved-evidence retrieval (TF-IDF top-4 + cited documents) → judge |
| B4 | EvalForge hybrid | rules → retrieval → structured judge → controls/uncertainty → human-review routing → final decision → audit record |
| A1–A4 | Ablations | B4 minus rules / minus retrieval / minus judge (replaced by EvalForge's lexical grader) / minus routing |

The exact decision rule is in the docstring of [`systems.py`](systems.py). It was fixed before any test-split result existed.

## Pre-registered hypotheses and decision rules

All hypotheses are evaluated on the **test** split (n=40) with the **LLM** judge (`config/default.yaml`). A hypothesis is:

- **supported** if the 95% paired-bootstrap CI of the stated difference excludes 0 in the predicted direction;
- **contradicted** if the CI excludes 0 in the opposite direction;
- **inconclusive** otherwise.

Inconclusive is the expected outcome for small effects at n=40. It is reported as such, never as support.

| ID | Hypothesis | Statistic |
|---|---|---|
| H1a/b/c | B4 has higher macro-F1 than B1 / B2 / B3 | Δ macro-F1 (B4 − baseline) |
| H2 | Grounding lowers false positives: FPR(B3) < FPR(B2) | Δ FPR (B3 − B2) |
| H3 | Removing rules lowers recall on format_error + missing_required_information | per-category recall, A1 vs B4 (descriptive; n=4 on test) |
| H4 | Routing concentrates errors: routing precision of B4 > B4 automated error rate | routing precision vs (1 − accuracy) (descriptive) |
| H5 | Removing retrieval lowers macro-F1: A2 < B4 | Δ macro-F1 (A2 − B4) |

The holdout split (n=20) is touched once, after the test-split analysis is written, to check that the direction of the effects holds. It is never used to change anything.

## Dataset

See [`DATASET_CARD.md`](DATASET_CARD.md): `evalforge-bench` v1.0.0, 80 synthetic single-author-labelled cases, 12-category taxonomy ([`taxonomy.py`](taxonomy.py)), dev/test/holdout, sha256-frozen.

## Metrics, statistics, protocol

- Metric definitions and null/abstention conventions: [`METRICS.md`](METRICS.md).
- Run procedure, tuning rules, and deviations log: [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md).
- Threats to validity: [`THREATS_TO_VALIDITY.md`](THREATS_TO_VALIDITY.md).
- External validation level achieved: [`EXTERNAL_VALIDATION.md`](EXTERNAL_VALIDATION.md).

## Error analysis

Every disagreement with the gold label is written to `disagreements.jsonl` with an automatic reason tag: rule false positive, judge false positive or false negative, gold evidence not retrieved, overconfident judge error, ambiguous gold label, or abstention. The generated `report.md` counts these tags per system and lists every B4 disagreement.

## Definition of research-ready

The repository contains:

- a frozen benchmark;
- documented baselines;
- reproducible experiment configs;
- statistical analysis;
- ablation results;
- failure analysis;
- a manuscript whose numbers are generated from committed experiment artifacts.

Status per item: see the checklist in [`README.md`](README.md).

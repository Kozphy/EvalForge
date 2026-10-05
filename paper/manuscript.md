# EvalForge: Auditable Hybrid Evaluation for AI-Generated Responses

## Abstract

Evaluation pipelines for AI-generated responses frequently rely on a single model judge, making results difficult to reproduce and audit. EvalForge is a local-first evaluation workbench that combines deterministic checks, evidence retrieval, optional structured model grading, and human review. This paper evaluates whether the hybrid design improves failure-detection quality and reduces false positives compared with simpler baselines. **This manuscript is a research scaffold; quantitative claims must be filled only from reproduced experimental results.**

## 1. Introduction

AI evaluation systems should do more than produce a score: they should expose why a decision was made, preserve evidence, and support reproducible comparison across model versions. EvalForge was designed around these requirements.

### Contributions

This work aims to contribute:

1. an auditable hybrid evaluation architecture;
2. a benchmark protocol separating development and held-out test cases;
3. paired comparisons against deterministic-only and model-judge baselines;
4. ablation analysis of rules, retrieval, model grading, and review routing;
5. a reproducible artifact linking paper claims to generated metrics.

## 2. Related Work

TODO: review literature on LLM-as-a-judge evaluation, evaluator bias, RAG evaluation, selective prediction/abstention, human-in-the-loop evaluation, and reproducibility in ML systems.

Do not add citations without verifying the primary source.

## 3. System

Describe:

- evaluation cases and requirements;
- deterministic graders;
- approved-evidence retrieval;
- optional structured model grader;
- confidence and review routing;
- human adjudication;
- immutable run/config snapshots and exports.

## 4. Research Questions and Hypotheses

Use the canonical definitions in `research/RESEARCH_PLAN.md`.

## 5. Benchmark

Document:

- domain and sampling procedure;
- inclusion/exclusion rules;
- train/dev/test split;
- annotation instructions;
- annotator expertise;
- agreement and adjudication;
- failure-category distribution;
- leakage controls.

## 6. Baselines

### B1: Deterministic-only

Rules without model grading or retrieval-assisted judgment.

### B2: Single model judge

A single evaluator model operating without approved-evidence retrieval.

### B3: Grounded model judge

A single evaluator model with retrieved approved evidence.

### B4: EvalForge hybrid

Rules + retrieval + model grader + uncertainty/review routing.

## 7. Experimental Protocol

Specify exact:

- repository commit SHA;
- benchmark version/hash;
- model/provider/version;
- prompts;
- temperature and sampling parameters;
- retrieval configuration;
- random seeds;
- machine/runtime environment;
- repeated-run policy;
- cost and latency measurement method.

## 8. Results

### 8.1 Primary metrics

| System | Accuracy | Precision | Recall | F1 | FPR | FNR |
|---|---:|---:|---:|---:|---:|---:|
| Deterministic-only | TBD | TBD | TBD | TBD | TBD | TBD |
| Single judge | TBD | TBD | TBD | TBD | TBD | TBD |
| Grounded judge | TBD | TBD | TBD | TBD | TBD | TBD |
| EvalForge hybrid | TBD | TBD | TBD | TBD | TBD | TBD |

### 8.2 Uncertainty

Report paired-bootstrap 95% confidence intervals for primary system differences.

### 8.3 Operational metrics

Report latency, model cost, abstention/review rate, and human-review effort.

## 9. Ablation Study

| Configuration | F1 | FPR | Latency | Review rate |
|---|---:|---:|---:|---:|
| Full hybrid | TBD | TBD | TBD | TBD |
| − deterministic rules | TBD | TBD | TBD | TBD |
| − retrieval | TBD | TBD | TBD | TBD |
| − model judge | TBD | TBD | TBD | TBD |
| − review routing | TBD | TBD | TBD | TBD |

## 10. Error Analysis

Analyze false positives and false negatives by the taxonomy in `research/RESEARCH_PLAN.md`. Include representative case IDs rather than cherry-picked prose-only anecdotes.

## 11. Threats to Validity

Discuss benchmark representativeness, subjective labels, development/test leakage, provider drift, prompt sensitivity, retrieval quality, dependence between cases, and measurement uncertainty.

## 12. Reproducibility

Every result table should be regenerable from versioned inputs and scripts. Record the exact command used to produce each artifact.

## 13. Conclusion

Summarize only findings supported by completed experiments. Do not convert intended hypotheses into claimed results.

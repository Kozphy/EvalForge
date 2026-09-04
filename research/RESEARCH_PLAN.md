# EvalForge Research Plan

## Working title

**EvalForge: Reliable Evaluation of AI-Generated Responses with Deterministic Rules, Evidence Grounding, and Human Review**

## Motivation

LLM-as-a-judge evaluation is convenient but can be unstable, opaque, and difficult to audit. EvalForge studies whether a hybrid evaluation pipeline can improve reliability by combining deterministic checks, evidence retrieval, optional model-based grading, and human adjudication.

## Research questions

### RQ1 — Detection quality
Does a hybrid evaluator detect response failures more accurately than a deterministic-only or single-judge baseline?

### RQ2 — False positives
Does evidence grounding reduce false-positive failure judgments compared with an ungrounded judge?

### RQ3 — Component contribution
Which components contribute most to performance: deterministic rules, retrieval grounding, model-based grading, or human review routing?

### RQ4 — Operational trade-offs
What accuracy, latency, and cost trade-offs arise across evaluator configurations?

## Hypotheses

- **H1:** Hybrid evaluation achieves higher macro-F1 than deterministic-only evaluation.
- **H2:** Evidence-grounded evaluation has a lower false-positive rate than an ungrounded model judge.
- **H3:** Removing deterministic checks causes a measurable drop in precision on format and instruction-following failures.
- **H4:** Human-review routing improves final adjudicated accuracy on low-confidence cases, at the cost of review effort.

## Experimental conditions

At minimum compare:

1. **Rule baseline** — deterministic checks only.
2. **Single judge baseline** — one model-based evaluator without retrieval grounding.
3. **Grounded judge** — model-based evaluator with approved evidence retrieval.
4. **EvalForge hybrid** — deterministic rules + grounding + confidence/review routing.

Optional fifth condition:

5. **EvalForge + human adjudication** — final reviewed outcome for uncertain cases.

## Dataset design

Each benchmark record should contain:

- stable case ID;
- prompt;
- candidate response;
- gold label;
- failure category;
- expected requirements;
- optional supporting evidence IDs;
- annotation provenance;
- annotator count;
- adjudicated label where applicable.

Recommended failure taxonomy:

- instruction_following;
- factual_grounding;
- citation_support;
- format_schema;
- code_syntax;
- sql_safety;
- unsupported_claim;
- omission;
- other.

Do not evaluate on the same hand-written examples used to tune grader rules. Maintain a held-out test partition.

## Primary metrics

- accuracy;
- macro precision;
- macro recall;
- macro F1;
- false-positive rate;
- false-negative rate.

## Secondary metrics

- latency per case;
- estimated model cost per case;
- human-review rate;
- coverage / abstention rate;
- inter-annotator agreement where multiple annotators exist.

## Statistical analysis

Report point estimates plus uncertainty. For the primary F1 comparison, use paired bootstrap resampling over benchmark cases and report a 95% confidence interval for the difference between systems.

Where appropriate, use McNemar's test for paired binary correctness outcomes. Treat statistical significance as supporting evidence, not as a substitute for effect size.

## Ablation study

Run the full hybrid system and then remove one component at a time:

- no deterministic rules;
- no retrieval grounding;
- no model judge;
- no uncertainty/review routing.

Measure changes in macro-F1, FPR, latency, and review rate.

## Error analysis

For every system, inspect false positives and false negatives by failure category. Record recurring failure modes and representative case IDs. Separate:

- grader error;
- ambiguous gold label;
- insufficient evidence;
- retrieval failure;
- model hallucination;
- rule over-trigger;
- rule under-trigger.

## Threats to validity

Track at least:

- benchmark size and representativeness;
- label subjectivity;
- leakage between rule development and test cases;
- model/provider drift;
- prompt sensitivity;
- retrieval corpus quality;
- dependence between benchmark cases;
- cost and latency measurement variance.

## Reproducibility target

A third party should be able to:

1. install dependencies;
2. obtain or generate the benchmark;
3. execute every baseline and EvalForge condition;
4. regenerate metrics and confidence intervals;
5. reproduce the tables used in the paper.

## Definition of research-ready

EvalForge is research-ready when the repository contains a frozen benchmark version, documented baselines, reproducible experiment configs, statistical analysis, ablation results, failure analysis, and a manuscript whose claims are traceable to generated artifacts.

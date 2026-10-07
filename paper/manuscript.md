# EvalForge: Auditable Hybrid Evaluation for AI-Generated Responses

## Abstract

Evaluation pipelines for AI-generated responses frequently rely on a single model judge, which makes results hard to reproduce and audit. EvalForge is a local-first evaluation workbench that combines deterministic checks, approved-evidence retrieval, a structured judge, uncertainty controls, and human-review routing. We ask whether this hybrid design detects AI-output failures more reliably than three simpler evaluators: deterministic-only, a single judge, and a grounded judge (RQ1). We also ask which components contribute (RQ2).

We release a frozen, hash-verified benchmark of 80 synthetic accounting question-answering cases with a 12-category failure taxonomy. It is single-author labelled (external validation level E0). We also release a harness that runs all four systems and four ablations on identical cases and writes immutable, auditable artifacts.

**Status.** The LLM-judge experiment that answers RQ1 has **NOT YET BEEN MEASURED**. The only completed run uses an offline, non-LLM stand-in judge. In that run the deterministic-only baseline is measured directly: high precision, low recall (Table 1b). The judge-based rows in that run validate the pipeline and are not evidence about LLM judging.

## 1. Introduction

AI evaluation systems should do more than produce a score. They should expose why a decision was made, preserve the evidence, and support reproducible comparison across model versions. EvalForge was designed around these requirements. This paper turns that design into a testable claim: if each component (rules, grounding, structured judging, routing) is useful, the combination should beat simpler evaluators on identical cases, and removing a component should cost something measurable.

### Contributions

This work provides:

1. an auditable hybrid evaluation architecture assembled from existing EvalForge components (Section 3);
2. `evalforge-bench` v1.0.0: a frozen benchmark with dev/test/holdout splits, per-case content hashes, leakage checks, and a holdout guard (Section 5);
3. a harness for paired comparison of the four systems and four ablations, with bootstrap CIs and exact McNemar tests (Sections 6-7);
4. per-run artifacts linking every table in this paper to generated metrics, raw judge outputs, and disagreement records (Section 12).

Contributions 3 and 4 are implemented. Their headline application, the LLM-judge comparison, is pending.

## 2. Related Work

*Sources below were checked against their arXiv abstract pages on 2026-10-07. No other citations are made.*

**LLM-as-a-judge.** Zheng et al. (2023, arXiv:2306.05685) study strong LLMs as judges of chat assistants. They report over 80% agreement with human preferences on MT-Bench and Chatbot Arena, and they document position, verbosity, and self-enhancement biases. Wang et al. (2023, arXiv:2305.17926) show that LLM evaluators' rankings can be manipulated by reordering candidate responses, and they propose calibration strategies including human-in-the-loop calibration. These results motivate two of our design choices: we never treat the judge as ground truth, and we keep deterministic checks that cannot be argued with.

**RAG evaluation.** Ragas (Es et al., 2023, arXiv:2309.15217) proposes reference-free metrics for retrieval-augmented generation, covering context relevance, faithfulness, and answer relevance. ARES (Saad-Falcon et al., 2023, arXiv:2311.09476) fine-tunes lightweight LM judges on synthetic data and uses a small human-annotated set for prediction-powered inference. Both evaluate generation *systems*. We instead evaluate *evaluators*: we score each evaluator's verdicts against labelled failures.

**Selective prediction.** Geifman and El-Yaniv (2017, arXiv:1705.08500) formalise selective classification, where a model rejects inputs to trade coverage for risk. EvalForge's human-review routing is a reject option. We report coverage, selective accuracy, and the share of automated errors that routing captures.

Literature on human-in-the-loop evaluation and ML reproducibility has **NOT YET** been reviewed for this draft.

## 3. System

Each case has a user prompt, a candidate response, and a `RequirementSpec` that a rule author could derive from the prompt alone (sentence/word limits, JSON keys, required terms, citation presence). The hybrid evaluator (B4) runs these stages:

1. **Deterministic rules** (`app.graders.check_rules`). Any failed rule is a final `fail`. The judge cannot override it.
2. **Approved-evidence retrieval** (`app.retrieval.retrieve`, TF-IDF, top-4 chunks merged per document), plus resolution of every `[KB-xx]` the response cites. A citation to a document that does not exist in the approved corpus is a deterministic `fail` (hallucinated source).
3. **Structured judge** (`research/judge.py`, prompt `judge-v1`). It sees the prompt, response, evidence, and rule results. It returns JSON with verdict, failure category, self-reported confidence, reason, and per-claim support. Unparseable output is preserved verbatim and yields no decision.
4. **Uncertainty controls** (`app.controls.evaluate_controls`). A contradicted claim or a citation outside the evidence set blocks the response, which becomes a `fail`. Low groundedness, low citation coverage, confidence below 0.7, or unresolved claims send it to review.
5. **Human-review routing.** A case whose decision rests on the judge is routed when controls return `review` or the judge output is unusable. Routing never changes the automated label; it is evaluated separately (Section 8.3).
6. **Audit record.** Every case gets its rule findings, evidence IDs, raw judge output, controls outcome, routing reasons, latency, and cost (`predictions.jsonl`, `evidence.jsonl`, `judge_raw.jsonl`).

The decision rule was fixed in code (`research/systems.py`) before any test-split result was produced.

## 4. Research Questions and Hypotheses

**RQ1.** Does a hybrid evaluation pipeline combining deterministic rules, evidence retrieval, structured LLM judging, and human-review routing detect AI-output failures more reliably than simpler evaluation approaches?

**RQ2.** Which components of the hybrid evaluator contribute most to accuracy, false-positive reduction, and review efficiency?

The pre-registered hypotheses (H1a-c: B4 beats B1/B2/B3 on macro-F1; H2: grounding lowers FPR; H3: rules drive recall on format and missing-information failures; H4: routing concentrates errors; H5: retrieval matters) and their decision rules are in `research/RESEARCH_PLAN.md`. A hypothesis counts as supported only if the 95% paired-bootstrap CI excludes zero in the predicted direction. **None has been tested yet**, because they all require the LLM-judge run.

## 5. Benchmark

`evalforge-bench` v1.0.0 (`research/DATASET_CARD.md`; dataset sha256 in `research/datasets/MANIFEST.json`):

| Property | Value |
|---|---|
| Domain | General accounting Q&A grounded in an 11-document approved knowledge base written for this benchmark |
| Sampling | Hand-written, not sampled. Each failing response contains one planted primary failure. Passing responses include correct refusals and abstentions, to probe false positives. |
| Splits | dev 20 (8 pass / 12 fail), test 40 (17 / 23), holdout 20 (8 / 12) |
| Taxonomy | 12 failure categories with a priority order for multi-failure cases (`research/taxonomy.py`) |
| Annotation | One annotator (the author) with AI drafting assistance. No independent annotation, no adjudication. Agreement NOT YET MEASURED. |
| Ambiguity | 3 cases flagged `ambiguous` (one per split) |
| Leakage controls | Unique IDs; no identical normalised prompts across splits; no cross-split prompt+response pairs with Jaccard ≥ 0.9; holdout loader guard; benchmark frozen and committed before the evaluator code |

## 6. Baselines and ablations

- **B1 Deterministic-only.** Rule checks only: any failed rule means `fail`, otherwise `pass`.
- **B2 Single judge.** One judge call, with no evidence, rules, or routing.
- **B3 Grounded judge.** Approved-evidence retrieval (including cited documents), then one judge call.
- **B4 EvalForge hybrid.** The full pipeline of Section 3.
- **Ablations of B4.**
  - A1 removes rules.
  - A2 removes retrieval and citation resolution.
  - A3 replaces the judge with EvalForge's lexical claim grader.
  - A4 removes routing.

All systems run on identical frozen cases in one run (`research/systems.py`).

## 7. Experimental Protocol

Each run's `manifest.json` records:

- git commit and dirty flag;
- dataset version and hash, plus case IDs;
- judge backend, model, and provider-reported model snapshot;
- prompt version and system-prompt hash;
- temperature and max tokens;
- retrieval configuration and routing policy;
- seed and bootstrap settings;
- exact command;
- Python, platform, and package versions;
- the sha256 of every artifact.

| Setting | Main experiment (`config/default.yaml`) | Smoke (`config/smoke.yaml`) |
|---|---|---|
| Judge | OpenAI `gpt-4o-mini`, temperature 0, max 600 tokens, prompt `judge-v1` | offline heuristic stand-in (`app.graders.heuristic_grade`), **not an LLM** |
| Split | test (n=40) | test (n=40) |
| Retrieval | TF-IDF, top-4 chunks + cited documents | same |
| Routing policy | min confidence 0.7, groundedness 0.75, citation coverage 0.75 | same |
| Seeds | experiment 20260924; bootstrap 2,000 iterations, seed 20260924 | bootstrap 1,000 iterations, seed 20260924 |
| Cost bound | $2.00 estimated, 2 retries, 60 s timeout | no API |
| Status | **NOT YET RUN** | committed: `research/results/smoke-offline-20261007T121705Z` |

**Repeated-run policy.** Each configuration runs once, at temperature 0. Raw outputs are kept so analyses can be replayed without new model calls. Run-to-run variance of the LLM judge is NOT YET MEASURED.

**Latency** is per-case wall-clock time: local compute plus judge API latency. **Cost** is estimated from a static token-price table, not taken from invoices (`research/METRICS.md`).

## 8. Results

### 8.1 Primary metrics

**Table 1a. LLM-judge experiment (answers RQ1).**

<!-- BEGIN GENERATED:llm-primary -->
NOT YET MEASURED. Run `python -m research.run --config research/config/default.yaml`, then `python -m research.paper_tables --experiment research/results/<experiment_id>`.
<!-- END GENERATED:llm-primary -->

**Table 1b. Smoke experiment with the offline stand-in judge.** Only the Deterministic-only row is a real measurement.

<!-- BEGIN GENERATED:smoke-primary -->
_Source: `research/results/smoke-offline-20261007T121705Z` · judge: offline heuristic stand-in (NOT an LLM) · split(s) ['test'] · n=40 · dataset `7e7c2d2c8b40` · commit `54ea98d` · 95% percentile bootstrap, 1000 iterations, seed 20260924. Generated by `python -m research.paper_tables`; do not edit._

> Judge-based rows use the offline heuristic stand-in, not an LLM. They demonstrate the pipeline. They are **not** evidence for RQ1 about LLM judging. Only the Deterministic-only row is a real measurement.

| System | Accuracy | Precision | Recall | Macro-F1 | FPR | FNR |
|---|---:|---:|---:|---:|---:|---:|
| Deterministic-only | 0.500 [0.350, 0.650] | 1.000 [1.000, 1.000] | 0.130 [0.000, 0.276] | 0.430 [0.286, 0.564] | 0.000 [0.000, 0.000] | 0.870 [0.724, 1.000] |
| Single judge (stand-in) | 0.575 [0.425, 0.725] | 0.575 [0.425, 0.725] | 1.000 [1.000, 1.000] | 0.365 [0.298, 0.420] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] |
| Grounded judge (stand-in) | 0.725 [0.575, 0.850] | 0.833 [0.647, 1.000] | 0.652 [0.448, 0.840] | 0.725 [0.575, 0.850] | 0.176 [0.000, 0.385] | 0.348 [0.160, 0.552] |
| EvalForge hybrid (stand-in) | 0.775 [0.625, 0.900] | 0.850 [0.682, 1.000] | 0.739 [0.550, 0.905] | 0.774 [0.625, 0.893] | 0.176 [0.000, 0.385] | 0.261 [0.095, 0.450] |
<!-- END GENERATED:smoke-primary -->

### 8.2 Uncertainty: paired differences

<!-- BEGIN GENERATED:llm-comparisons -->
LLM-judge paired comparisons: NOT YET MEASURED.
<!-- END GENERATED:llm-comparisons -->

<!-- BEGIN GENERATED:smoke-comparisons -->
_Source: `research/results/smoke-offline-20261007T121705Z` · judge: offline heuristic stand-in (NOT an LLM) · split(s) ['test'] · n=40 · dataset `7e7c2d2c8b40` · commit `54ea98d` · 95% percentile bootstrap, 1000 iterations, seed 20260924. Generated by `python -m research.paper_tables`; do not edit._

| Comparison (B − A) | Δ accuracy [95% CI] | Δ macro-F1 [95% CI] | Δ FPR [95% CI] | McNemar p |
|---|---:|---:|---:|---:|
| Grounded judge (stand-in) − Single judge (stand-in) | +0.150 [-0.075, 0.351] | +0.360 [0.188, 0.517] | -0.824 [-1.000, -0.615] | 0.286 |
| EvalForge hybrid (stand-in) − Deterministic-only | +0.275 [0.100, 0.475] | +0.344 [0.171, 0.511] | +0.176 [0.000, 0.385] | 0.013 |
| EvalForge hybrid (stand-in) − Single judge (stand-in) | +0.200 [-0.025, 0.400] | +0.409 [0.246, 0.545] | -0.824 [-1.000, -0.615] | 0.115 |
| EvalForge hybrid (stand-in) − Grounded judge (stand-in) | +0.050 [0.000, 0.125] | +0.049 [0.000, 0.119] | +0.000 [0.000, 0.000] | 0.500 |
<!-- END GENERATED:smoke-comparisons -->

### 8.3 Operational metrics and review efficiency

<!-- BEGIN GENERATED:llm-operational -->
LLM-judge latency, cost, agreement, and routing: NOT YET MEASURED.
<!-- END GENERATED:llm-operational -->

<!-- BEGIN GENERATED:smoke-operational -->
_Source: `research/results/smoke-offline-20261007T121705Z` · judge: offline heuristic stand-in (NOT an LLM) · split(s) ['test'] · n=40 · dataset `7e7c2d2c8b40` · commit `54ea98d` · 95% percentile bootstrap, 1000 iterations, seed 20260924. Generated by `python -m research.paper_tables`; do not edit._

| System | Abstention | Human-review rate | Judge-gold agreement (κ) | Latency p50 / p95 ms | Cost/case USD |
|---|---:|---:|---:|---:|---:|
| Deterministic-only | 0.000 | 0.000 | n/a | 0.02 / 0.04 | 0.000000 |
| Single judge (stand-in) | 0.000 | 0.000 | 0.575 (0.000) | 0.09 / 0.30 | 0.000000 |
| Grounded judge (stand-in) | 0.000 | 0.000 | 0.700 (0.413) | 5.69 / 7.45 | 0.000000 |
| EvalForge hybrid (stand-in) | 0.000 | 0.225 | 0.700 (0.413) | 7.04 / 10.20 | 0.000000 |
| Hybrid - rules (stand-in) | 0.000 | 0.250 | 0.700 (0.413) | 5.83 / 8.06 | 0.000000 |
| Hybrid - retrieval (stand-in) | 0.000 | 0.925 | 0.575 (0.000) | 0.25 / 0.44 | 0.000000 |
| Hybrid - judge (stand-in) | 0.000 | 0.225 | 0.750 (0.504) | 5.37 / 7.16 | 0.000000 |
| Hybrid - routing (stand-in) | 0.000 | 0.000 | 0.700 (0.413) | 7.35 / 13.89 | 0.000000 |

| System | Routed | Error capture | Routing precision | Selective accuracy | Oracle-resolved accuracy (simulated reviewer) |
|---|---:|---:|---:|---:|---:|
| EvalForge hybrid (stand-in) | 9/40 | 0.111 | 0.111 | 0.742 | 0.800 |
| Hybrid - rules (stand-in) | 10/40 | 0.091 | 0.100 | 0.667 | 0.750 |
| Hybrid - retrieval (stand-in) | 37/40 | 1.000 | 0.459 | 1.000 | 1.000 |
| Hybrid - judge (stand-in) | 9/40 | 0.111 | 0.111 | 0.742 | 0.800 |
<!-- END GENERATED:smoke-operational -->

## 9. Ablation Study

<!-- BEGIN GENERATED:llm-ablation -->
LLM-judge ablations: NOT YET MEASURED.
<!-- END GENERATED:llm-ablation -->

<!-- BEGIN GENERATED:smoke-ablation -->
_Source: `research/results/smoke-offline-20261007T121705Z` · judge: offline heuristic stand-in (NOT an LLM) · split(s) ['test'] · n=40 · dataset `7e7c2d2c8b40` · commit `54ea98d` · 95% percentile bootstrap, 1000 iterations, seed 20260924. Generated by `python -m research.paper_tables`; do not edit._

> Judge-based rows use the offline heuristic stand-in, not an LLM. They demonstrate the pipeline. They are **not** evidence for RQ1 about LLM judging. Only the Deterministic-only row is a real measurement.

| Configuration | Macro-F1 [95% CI] | FPR | Δ macro-F1 vs full [95% CI] | Latency p50 ms | Review rate |
|---|---:|---:|---:|---:|---:|
| Full hybrid | 0.774 [0.625, 0.893] | 0.176 | - | 7.04 | 0.225 |
| − deterministic rules | 0.725 [0.575, 0.850] | 0.176 | -0.049 [-0.119, 0.000] | 5.83 | 0.250 |
| − retrieval | 0.365 [0.298, 0.420] | 1.000 | -0.409 [-0.545, -0.246] | 0.25 | 0.925 |
| − judge (lexical grader instead) | 0.774 [0.625, 0.893] | 0.176 | +0.000 [0.000, 0.000] | 5.37 | 0.225 |
| − review routing | 0.774 [0.625, 0.893] | 0.176 | +0.000 [0.000, 0.000] | 7.35 | 0.000 |
<!-- END GENERATED:smoke-ablation -->

In the smoke run, A3 (minus judge) is identical to B4 by construction: the stand-in judge and the lexical grader are the same heuristic. That ablation is therefore uninformative until the LLM run.

## 10. Error Analysis

<!-- BEGIN GENERATED:llm-errors -->
LLM-judge error analysis: NOT YET MEASURED.
<!-- END GENERATED:llm-errors -->

<!-- BEGIN GENERATED:smoke-errors -->
_Source: `research/results/smoke-offline-20261007T121705Z` · judge: offline heuristic stand-in (NOT an LLM) · split(s) ['test'] · n=40 · dataset `7e7c2d2c8b40` · commit `54ea98d` · 95% percentile bootstrap, 1000 iterations, seed 20260924. Generated by `python -m research.paper_tables`; do not edit._

| System | Disagreements | False positives | False negatives | Abstained | Overconfident | Gold evidence not retrieved | Ambiguous-gold cases |
|---|---:|---:|---:|---:|---:|---:|---:|
| Deterministic-only | 20 | 0 | 20 | 0 | 0 | 0 | 1 |
| Single judge (stand-in) | 17 | 17 | 0 | 0 | 0 | 0 | 0 |
| Grounded judge (stand-in) | 11 | 3 | 8 | 0 | 10 | 0 | 1 |
| EvalForge hybrid (stand-in) | 9 | 3 | 6 | 0 | 8 | 0 | 1 |
| Hybrid - rules (stand-in) | 11 | 3 | 8 | 0 | 10 | 0 | 1 |
| Hybrid - retrieval (stand-in) | 17 | 17 | 0 | 0 | 0 | 0 | 0 |
| Hybrid - judge (stand-in) | 9 | 3 | 6 | 0 | 8 | 0 | 1 |
| Hybrid - routing (stand-in) | 9 | 3 | 6 | 0 | 8 | 0 | 1 |

Hybrid (B4) false negatives by gold category: ambiguous_case: EFB-060; calculation_error: EFB-047; factual_error: EFB-038, EFB-039; missing_required_information: EFB-055; retrieval_grounding_failure: EFB-045.
Hybrid (B4) false positives: EFB-023, EFB-030, EFB-034.
<!-- END GENERATED:smoke-errors -->

These findings come from the smoke run (`research/results/smoke-offline-20261007T121705Z/report.md` and `disagreements.jsonl`):

- **Deterministic rules are precise but blind to content.** B1 produced no false positives. It caught only failures that the prompt made checkable: a missing JSON key (EFB-058), a word limit (EFB-059), and a missing "credit" term (EFB-054). It missed every factual, calculation, reasoning, grounding, hallucination, unsafe, unsupported-claim, and instruction-violation failure. The omission in EFB-055 had no checkable requirement and was also missed.
- **The lexical stand-in "detects" failures for the wrong reason.** It flags any claim with low word overlap with the evidence. Without evidence (B2, A2) it therefore flags almost everything, and with evidence (B3) it misses contradictions whose wording overlaps the evidence, such as EFB-038 ("depreciation generates cash") and EFB-039 (a three-year lease called short-term). Its per-category recall must not be read as content understanding.
- **Routing driven by the stand-in's confidence is uninformative (a negative result for the mechanism, not for routing in general).** In B4, 9 cases were routed but only 1 of them was an automated error: routing precision 0.111, below the 0.225 automated error rate. A confidence signal that does not track correctness cannot make routing efficient. The LLM run tests whether self-reported LLM confidence does better.

## 11. Threats to Validity

Summarised from `research/THREATS_TO_VALIDITY.md`:

- **Labels and authorship.** Single-author labels, with the same person writing the cases, rules, and evaluator.
- **Planted failures.** Planted, single-failure responses are likely easier than organic errors.
- **Sample size.** n = 40 on test, so one case equals 2.5 accuracy points, and per-category cells hold 1-3 cases.
- **Prevalence.** Failure prevalence of 57-60% is far above realistic traffic.
- **Judge model.** One judge model is used, and provider snapshots drift.
- **Statistics.** No multiple-comparison correction is applied, and case dependence (shared documents and templates) may make the CIs too narrow.
- **Measurement.** Cost is estimated rather than billed, and latency includes warm-up.

## 12. Reproducibility

```bash
pip install -r requirements.txt
python -m research.dataset check
python -m research.run --config research/config/smoke.yaml
python -m research.run --verify research/results/smoke-offline-20261007T121705Z
python -m research.paper_tables --experiment research/results/smoke-offline-20261007T121705Z
```

The tables in Sections 8-10 are regenerated by the last command, which refuses results whose artifact hashes no longer match the manifest. CI runs the smoke experiment on every push. An independent reproduction (E3) has NOT YET happened.

## 13. Conclusion

Supported by completed runs:

1. On this synthetic benchmark, deterministic rules alone are high-precision and low-recall (Table 1b). They catch only failures that the prompt makes mechanically checkable.
2. The harness produces paired, hash-verified, fully auditable comparisons of four evaluators and four ablations on identical cases.

Not yet supported:

- **RQ1** (whether the hybrid beats single and grounded LLM judges) and **RQ2** (which components matter) remain open until the pre-registered LLM-judge run on test is executed and analysed.
- Even after that run, the evidence level stays E0 (synthetic cases, one author's labels) until independent annotation (E1) or a public benchmark (E2) is added.

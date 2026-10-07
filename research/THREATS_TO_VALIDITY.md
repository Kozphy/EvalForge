# Threats to validity

## Construct validity

- **Gold labels are one author's judgement.** No second annotator, no adjudication, and no inter-annotator agreement. "Judge-human agreement" therefore means agreement with one person who also designed the system.
- **Planted failures.** Every failing response was written to contain one clean primary failure. Organic model errors are messier, so detection rates here likely **overstate** real-world performance for every system.
- **Binary pass/fail** hides severity. A format slip and fraud advice each count as one false negative.
- **Taxonomy priority order** forces a single category onto multi-failure cases. This affects category accuracy, not binary metrics.

## Internal validity

- **Author-evaluator overlap.** The same person wrote the cases, the requirements, the rules, the judge prompt, and the decision rule. Requirements were written to be derivable from the prompt alone, never from the gold answer, but bias toward rule-friendly cases cannot be excluded.
- **Judge prompt was not tuned on test.** It was drafted before freezing and debugged on dev with the offline stand-in. It has **not** been debugged with the real LLM on dev. The first LLM run may surface prompt problems, which would then have to be logged as deviations.
- **Retrieval includes cited documents.** This helps the judge detect wrong-source citations. It also means retrieval quality is partly driven by the response under test.
- **Offline stand-in ≠ LLM.** Smoke results for B2–B4 measure plumbing, not LLM judging. Only B1 smoke numbers are a real measurement.

## External validity

- **Synthetic, English, single domain** (textbook accounting), with short answers and a uniform citation format `[KB-xx]`.
- **Failure prevalence of 57-60%** is far above realistic traffic, so precision and FPR do not transfer to production base rates.
- **One judge model** in the default config (`gpt-4o-mini`). Results do not generalise to other models or to future snapshots of the same model; the provider-reported model version is recorded in the manifest.

## Statistical conclusion validity

- **n = 40 (test).** One case is 2.5 accuracy points, and CIs will be wide. Per-category results (n = 1-3) are descriptive only.
- **Multiple comparisons.** There are three primary comparisons, four ablations, and one grounding comparison. No correction is applied; CIs are reported for all of them, and none is cherry-picked.
- **Cases are not independent.** Several cases share a knowledge-base document and a question template, so bootstrap CIs may be too narrow.

## Measurement

- **Cost** is estimated from a static price table, not billed amounts.
- **Latency** includes network variance and first-call warm-up (scikit-learn import on the first retrieval call). p95 is sensitive to this.
- **Provider nondeterminism.** Temperature 0 does not guarantee identical outputs across calls or days. Raw outputs are preserved so analyses can be replayed (`judge.backend: replay`) without new calls.

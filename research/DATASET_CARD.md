# Dataset card: evalforge-bench v1.0.0

| Field | Value |
|---|---|
| Name / version | `evalforge-bench` / `1.0.0` (frozen 2026-09-24) |
| Dataset hash | `dataset_sha256` in [`datasets/MANIFEST.json`](datasets/MANIFEST.json) |
| Task | Binary judgement of a candidate AI answer: `pass` (acceptable) or `fail` (material failure), plus one primary failure category |
| Domain | General accounting Q&A grounded in an 11-document approved knowledge base |
| Size | 80 cases: dev 20, test 40, holdout 20 |
| Provenance | **Synthetic.** Written for this benchmark by the repository author with AI drafting assistance. Not production data, not user data. |
| Labels | Single-author judgement. **Not independently adjudicated** (no second annotator; inter-annotator agreement NOT YET MEASURED). |
| External validation | Level E0 (see [EXTERNAL_VALIDATION.md](EXTERNAL_VALIDATION.md)) |
| License | Same as repository |

## Files

| Path | Content |
|---|---|
| `datasets/corpus/kb.jsonl` | Approved evidence corpus `KB-01`..`KB-11` (original wording; accounting concepts follow IFRS / US GAAP at a textbook level) |
| `datasets/{dev,test,holdout}/cases.jsonl` | Frozen cases, one JSON object per line, canonical key order, LF endings |
| `datasets/MANIFEST.json` | sha256 per file, case IDs per split, label and category distribution, combined `dataset_sha256` |
| `datasets/source_v1.py` | Human-readable authoring source. `python -m research.dataset check` fails if it drifts from the frozen files |

## Case schema

| Field | Meaning |
|---|---|
| `case_id` | Immutable ID `EFB-NNN`; never reused across versions |
| `split` | `dev` (protocol design, judge-prompt debugging), `test` (primary reported results), `holdout` (final confirmation run only; loader refuses it without an explicit flag) |
| `prompt` | User question, including any explicit constraints (length, JSON, "cite the source", policy) |
| `candidate_response` | The AI answer being evaluated (hand-written to contain zero or one primary failure) |
| `requirements` | `app.schemas.RequirementSpec` a rule author could plausibly write *from the prompt alone* (sentence/word limits, JSON keys, "debit"/"credit" terms, citation presence). Requirements never encode the gold answer |
| `gold_label` | `pass` or `fail` |
| `failure_category` | One of [`research/taxonomy.py`](taxonomy.py); `none` for passes |
| `gold_evidence_ids` | Knowledge-base documents that settle the case |
| `label_rationale` | Why the gold label holds |
| `ambiguous` | `true` when reasonable reviewers could disagree (3 cases, all `ambiguous_case`) |
| `content_sha256` | Hash of the labelled content; validation rejects edited cases |

## Distribution

| Split | pass | fail | Categories present |
|---|---:|---:|---|
| dev | 8 | 12 | all 12 failure categories once |
| test | 17 | 23 | factual 3, calculation 3, unsupported 2, hallucination 2, grounding 2, reasoning 2, instruction 2, missing info 2, unsafe 2, format 2, ambiguous 1 (`other` absent) |
| holdout | 8 | 12 | all 12 failure categories once |

Failure prevalence is 57-60% per split. This is higher than in realistic traffic, so precision and false-positive-rate figures do not transfer directly to production base rates.

## Taxonomy

Twelve failure categories plus `none`. When a response has several problems, the annotator picks the first category in `research/taxonomy.py::PRIORITY`: unsafe output, then hallucination, factual error, calculation error, reasoning error, unsupported claim, retrieval/grounding failure, missing required information, instruction violation, format error, ambiguous, other. The definitions are in `taxonomy.DEFINITIONS`.

## Construction and known biases

- **Same-author bias.** The person who wrote the candidate responses also wrote the labels, the rules, and the evaluator. The failures are therefore "planted" and probably cleaner than organic model errors.
- **Single domain, English only, short answers** of one to three sentences.
- **Small n.** Confidence intervals on test (n=40) are wide; per-category results (n=2-3) are descriptive only.
- **Citation format is uniform** (`[KB-xx]`). This makes citation-existence checks easier than they would be on real outputs.
- **Requirements bias.** Cases that ask for JSON, word limits, or "debit and credit" give deterministic rules a fair chance, and those cases are a minority by design.

## Leakage controls

- Case IDs are unique across splits.
- No identical normalised prompts across splits, and no cross-split prompt+response pairs with token Jaccard ≥ 0.9. Both checks run in `research.dataset.freeze` and in the tests.
- The holdout loader requires `allow_holdout=True`. The runner requires `--allow-holdout`, and the result manifest records whether holdout was used.
- Judge prompts were drafted before freezing and may be debugged on dev only.

## Intended use / non-use

- **Intended use:** comparing evaluator designs on identical frozen cases, and studying evaluator failure modes.
- **Not for:** claims about production error rates, accounting-advice quality, or the behaviour of any specific deployed model.

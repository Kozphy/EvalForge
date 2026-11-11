# Annotation, Agreement, and Classification Evaluation (P0)

The `annotation_eval` package adds label-provenance-aware evaluation for
sentiment, content moderation, inter-annotator agreement, and human response
rubrics. It runs fully offline and needs no API keys.

## What it is and is not

| Component | What it is | What it is not |
| --- | --- | --- |
| `schema.py` | `LabelProvenance` and `PredictorKind` on every label and prediction | Proof that any label is human |
| `metrics.py` | Multi-class confusion matrix, per-class P/R/F1, macro and weighted F1; refuses self-comparison | A benchmark |
| `agreement.py` | Percent agreement, Cohen's kappa, disagreement listing, explicit adjudication | Human agreement unless inputs are human |
| `baselines.py` | Rule-based keyword and regex baselines | Trained ML classifiers |
| `rubric.py` | `HumanResponseRubric` with anchored 1-5 criteria and rater provenance | Auto-generated scores |
| `data/` | SYNTHETIC fixtures (20 sentiment, 20 moderation, 24 simulated annotations) | Human annotations or real user data |

## Provenance rules

- Gold labels in `data/` are `synthetic_author`: written by an AI coding
  assistant together with the sentences. The same author wrote the rule-based
  baselines, so the two are **not independent** and the scores below are a
  harness smoke test only.
- Agreement data uses `simulated_annotator` rows from two scripted
  annotators. Reports set `is_human_agreement: false`.
- `evaluate_predictions(..., require_human_gold=True)` fails unless every gold
  label is `human_independent` or `adjudicated_human`.
- Placeholder identities ending in `@example.com` are rejected for annotators
  and raters.
- Every dataset is pinned by sha256 in `data/MANIFEST.json`; a mismatch raises
  `ManifestMismatchError`.

## Run

```bash
python -m annotation_eval sentiment
python -m annotation_eval moderation
python -m annotation_eval agreement
pytest tests/test_annotation_eval_*.py
```

## Current fixture output (rule-based baseline on synthetic labels)

| Task | n | Accuracy | Macro F1 | Errors |
| --- | --- | --- | --- | --- |
| Sentiment | 20 | 0.90 | 0.9011 | s12 (sarcasm), s18 (implicit praise) |
| Moderation | 20 | 0.80 | 0.8115 | m09, m13, m14, m18 |
| Agreement (simulated) | 12 shared | 0.75 agreement | kappa 0.625 | s05, s09, s12 |

These numbers only show that the harness computes metrics correctly and
surfaces errors. They are not evidence of real sentiment or moderation
quality.

## Next steps to make results meaningful

1. Collect labels from at least two independent people blind to the rules,
   store them as `human_independent`, and report kappa before adjudication.
2. Score a predictor written by someone other than the label author, or a
   trained model with a held-out split.
3. Add public, license-checked datasets only after recording their license in
   the manifest.

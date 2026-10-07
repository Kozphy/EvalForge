# Metrics

All metrics are computed by [`metrics.py`](metrics.py) and [`analysis.py`](analysis.py) from `predictions.jsonl`. The positive class is **`fail`**: detecting a failure is a positive.

## Conventions

| Situation | Treatment |
|---|---|
| System produced no decision (`predicted_label = null`: judge output unparseable, provider error, crash) | Counted as an **error** for accuracy. It is a **false negative** if gold is `fail` and is **never a false positive**. It is reported separately as `abstention_rate`. |
| Metric denominator is zero (e.g. precision when nothing is predicted `fail`) | `null` (undefined), never 0 |
| A class is never predicted, but it has gold members | Its recall is a defined 0, so its F1 is 0 (not null) |
| Operational value not measured (cost without a price table, failed call) | `null` + `note: "NOT MEASURED: ..."`; never 0 |
| Local-only systems (no API) | `cost_per_case_usd = 0.0` with `basis: "no paid API calls"`. This is a measured zero, not missing data. |

## Primary metrics (automated decision)

| Metric | Definition |
|---|---|
| accuracy | (TP + TN) / n, with abstentions counted wrong |
| precision | TP / (TP + FP) |
| recall | TP / (all gold `fail`) |
| f1 | harmonic mean of precision and recall for the `fail` class |
| macro_f1 | mean of the F1 for `fail` and the F1 for `pass` |
| false_positive_rate (FPR) | FP / (all gold `pass`): acceptable answers wrongly flagged |
| false_negative_rate (FNR) | (FN + abstained gold-fail) / (all gold `fail`): failures missed |

## Operational and review metrics

| Metric | Definition |
|---|---|
| abstention_rate | abstained / n |
| human_review_rate | routed / n. It is 0.0 for systems without routing (`routing_enabled: false`). |
| judge_human_agreement | share of judged cases where the raw judge verdict equals the gold label, plus Cohen's κ. This is the judge **before** rules or controls. Gold labels come from one author, so this is agreement with that author, not with "humans" in general. |
| latency_ms | per-case wall clock: local compute + judge API latency. Cache hits are charged the original call's latency so that ablations reflect deployment cost. Reported as mean / p50 / p95. |
| cost_per_case_usd | estimated judge spend / n, using `finance_eval.live.PRICE_PER_1M`. This is an estimate, not an invoice. Cache hits are charged the original cost. Actual spend is `manifest.judge.estimated_spend_usd`. |
| error_capture_rate | automated errors that were routed / all automated errors |
| routing_precision | routed cases that were automated errors / all routed cases |
| coverage, selective accuracy | share of cases not routed, and accuracy on those cases |
| oracle_resolved accuracy | accuracy if every routed case received the gold label. This is a **simulated perfect reviewer** (an upper bound), not measured human performance. |
| per_category_recall | for each gold failure category, the share predicted `fail` (descriptive; n = 1-3 per category) |
| category_accuracy_on_true_positives | among correctly flagged failures, the share whose predicted category matches gold |
| gold_evidence_recall | share of cases whose gold evidence documents were all in the evidence set (retrieval systems only) |

## Uncertainty and paired tests

- **95% CIs:** percentile bootstrap over cases. Iterations and seed come from the config (`bootstrap.iterations`, `bootstrap.seed`); the same seed gives identical output. Resamples where a metric is undefined are skipped, and their count is reported (`valid_resamples`).
- **Paired comparisons:** the same resampled case indices are used for both systems, and the CI is on metric(B) − metric(A).
- **McNemar:** exact two-sided binomial test on discordant per-case correctness (A right / B wrong vs A wrong / B right).
- **Significance does not substitute for effect size.** With n = 40, a 2.5-point accuracy difference is a single case.

## Judge confidence

Judge `confidence` is the model's self-report. It has **not** been calibrated, and it is never presented as a probability. "Overconfident error" means confidence ≥ 0.8 on a wrong verdict, which is a descriptive threshold only.

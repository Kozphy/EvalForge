# Analyses

Analyses are generated per experiment, so they cannot drift from the data:

- `research/results/<experiment_id>/report.md`: metrics with CIs, review efficiency, paired comparisons, per-category recall, error-analysis tag counts, and every B4 disagreement.
- `research/results/<experiment_id>/disagreements.jsonl`: one record per system/case disagreement with the gold label.

| Experiment | Judge | Split | Status |
|---|---|---|---|
| `smoke-offline-*` | offline heuristic stand-in (not an LLM) | test | committed; only the B1 rows are a real measurement |
| `rq1-llm-gpt-4o-mini-*` | gpt-4o-mini | test | NOT YET MEASURED |
| holdout confirmation | gpt-4o-mini | holdout | NOT YET MEASURED |

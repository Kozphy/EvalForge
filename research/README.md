# EvalForge Research & Reproducibility

This directory turns EvalForge from an evaluation product into a testable research artifact.

**Question.** Does a hybrid evaluator (rules → evidence retrieval → structured judge → uncertainty controls → human-review routing) detect AI-output failures more reliably than a deterministic-only checker, a single LLM judge, or a grounded judge (RQ1)? And which components matter (RQ2)?

**Evidence level.** Everything here is a **local benchmark on synthetic, single-author-labelled data** (external validation level E0). Nothing here is production evidence.

## Reproduce in two commands

```bash
pip install -r requirements.txt
python -m research.dataset check                              # frozen benchmark hashes match MANIFEST.json
python -m research.run --config research/config/smoke.yaml    # offline, no API key, seconds
```

The second command writes `research/results/smoke-offline-<timestamp>/`, containing `manifest.json`, `predictions.jsonl`, `evidence.jsonl`, `judge_raw.jsonl`, `disagreements.jsonl`, `errors.jsonl`, `metrics.json`, `confidence_intervals.json`, and `report.md`.

The LLM-judge experiment is `python -m research.run --config research/config/default.yaml`. It needs `OPENAI_API_KEY` and has a $2.00 estimated-spend cap.

## Map

| File | Purpose |
|---|---|
| [`RESEARCH_PLAN.md`](RESEARCH_PLAN.md) | RQs, systems, pre-registered hypotheses and decision rules |
| [`DATASET_CARD.md`](DATASET_CARD.md) | evalforge-bench v1.0.0: provenance, schema, distribution, biases |
| [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md) | Order of work, tuning rules, artifacts, deviations log |
| [`METRICS.md`](METRICS.md) | Definitions, null/abstention conventions, statistics |
| [`THREATS_TO_VALIDITY.md`](THREATS_TO_VALIDITY.md) | What could make the conclusions wrong |
| [`EXTERNAL_VALIDATION.md`](EXTERNAL_VALIDATION.md) | E0-E5 ladder; only E0 achieved |
| `datasets/` | Frozen corpus + dev/test/holdout JSONL + `MANIFEST.json`; `source_v1.py` is the authoring source |
| `taxonomy.py`, `dataset.py` | Failure taxonomy; validation, hashing, leakage checks, holdout guard |
| `judge.py`, `systems.py` | Judge prompt/parsing/backends; B1-B4 and ablations A1-A4 |
| `run.py`, `analysis.py`, `metrics.py` | Runner, aggregation/report, statistics |
| `paper_tables.py` | Writes manuscript tables from a results directory |
| `config/` | `smoke.yaml` (offline), `default.yaml` (LLM judge) |
| `results/` | Committed raw experiment outputs (immutable; hash-verified) |
| `analysis/`, `paper/` | Pointers to generated analyses and the manuscript |

## Definition-of-done status

| Item | Status |
|---|---|
| Frozen, versioned benchmark with hashes, provenance, taxonomy, no cross-split duplicates | Done |
| B1-B4 implemented on identical cases | Done |
| Ablations (minus rules / retrieval / judge / routing) | Done (implemented; LLM results NOT YET MEASURED) |
| Bootstrap CIs, paired bootstrap, exact McNemar, deterministic seeds | Done |
| Disagreement records + error analysis | Done (generated per run) |
| Smoke experiment, no paid API | Done |
| Default LLM-judge experiment on test | **NOT YET MEASURED**: needs an API key and approval of spend |
| Holdout confirmation run | **NOT YET MEASURED** |
| Manuscript tables generated from outputs | Done for the smoke run; LLM rows NOT YET MEASURED |
| External validation beyond E0 | Not achieved |

## Legacy paired-prediction CLI

`run_analysis.py` still analyses a CSV with one prediction column per system:

```bash
python -m research.run_analysis research/example_predictions.csv \
  --systems rule_baseline evalforge_hybrid --compare rule_baseline evalforge_hybrid --iterations 2000 --seed 42
```

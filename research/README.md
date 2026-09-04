# EvalForge Research & Reproducibility

This directory turns EvalForge from an evaluation product into a testable research artifact.

## Start here

Read [`RESEARCH_PLAN.md`](RESEARCH_PLAN.md) for the research questions, hypotheses, baselines, metrics, ablations, and validity threats.

## Benchmark contract

Benchmark records should conform to [`benchmark_schema.json`](benchmark_schema.json).

Keep development data separate from the held-out test set. Do not tune grader rules against the final test partition.

## Analyze paired predictions

The analysis CLI expects one row per benchmark case and one prediction column per system.

```bash
python -m research.run_analysis research/example_predictions.csv \
  --systems rule_baseline evalforge_hybrid \
  --compare rule_baseline evalforge_hybrid \
  --iterations 2000 \
  --seed 42
```

The command writes `research/results/metrics.json` and prints the same report.

The report includes:

- accuracy;
- precision;
- recall;
- F1;
- false-positive rate;
- false-negative rate;
- confusion counts;
- paired-bootstrap 95% confidence interval when `--compare` is supplied.

## Experiment protocol

For each experiment, record:

1. repository commit SHA;
2. benchmark version or content hash;
3. exact system configuration;
4. provider/model version when applicable;
5. prompt version;
6. retrieval settings;
7. random seed;
8. timestamp and environment;
9. output artifact path.

Never overwrite a published result without retaining enough metadata to reproduce the earlier version.

## Recommended result layout

```text
research/
├── results/
│   ├── experiment-001/
│   │   ├── predictions.csv
│   │   ├── metrics.json
│   │   ├── config.json
│   │   └── notes.md
│   └── experiment-002/
└── ...
```

## Research quality gate

Before making a quantitative claim in `paper/manuscript.md`, verify that:

- the benchmark is frozen and versioned;
- the compared systems use the same cases;
- test cases were not used to tune rules;
- the result can be regenerated from a documented command;
- uncertainty is reported for primary comparisons;
- failure cases have been manually inspected;
- limitations and negative results are preserved.

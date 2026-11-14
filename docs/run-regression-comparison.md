# Run regression comparison

EvalForge can compare a candidate evaluation run against a baseline and turn the result into an explicit quality-gate decision.

## Why this exists

Aggregate accuracy alone can hide important failures. A candidate run may improve overall while introducing new major-severity regressions. The comparison service therefore reports both metric deltas and case-level changes.

## CLI

```bash
python scripts/compare_runs.py 42 57 \
  --max-accuracy-drop 0.02 \
  --max-new-major-regressions 0 \
  --fail-on-regression
```

Arguments:

- `42` is the baseline run ID.
- `57` is the candidate run ID.
- `--max-accuracy-drop` sets the permitted absolute accuracy decrease.
- `--max-new-major-regressions` limits newly incorrect cases whose candidate label is `major` or `critical`.
- `--fail-on-regression` returns exit code `1` when the gate fails, making the command suitable for CI.

Use repeated `--major-label` arguments to override the default major labels.

```bash
python scripts/compare_runs.py 42 57 \
  --major-label severe \
  --major-label blocker
```

## Output

The JSON report includes:

- gate decision and policy violations;
- baseline, candidate, and delta values for shared numeric metrics;
- newly regressed cases;
- resolved failures;
- changed predictions and human-review routing;
- added and removed case keys.

Example:

```json
{
  "decision": "fail",
  "summary": {
    "comparable_cases": 125,
    "changed_cases": 8,
    "new_regressions": 3,
    "resolved_failures": 5,
    "new_major_regressions": 1,
    "added_cases": 0,
    "removed_cases": 0
  },
  "violations": [
    {
      "rule": "max_new_major_regressions",
      "allowed": 0,
      "actual": 1
    }
  ]
}
```

## Loop-engineering use

This comparison is designed to act as an evidence gate inside an agent or CI loop:

```text
change prompt, grader, or retrieval settings
→ execute candidate run
→ compare with approved baseline
→ pass, repair, or escalate to human review
```

The loop should only declare success when the comparison decision is `pass` and the project’s normal test suite also succeeds.

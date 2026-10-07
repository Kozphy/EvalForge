# Paper

The manuscript is at [`paper/manuscript.md`](../../paper/manuscript.md), in the repository root.

Its results tables sit between `<!-- BEGIN GENERATED:<id> -->` / `<!-- END GENERATED:<id> -->` markers. They are rewritten by:

```bash
python -m research.paper_tables --experiment research/results/<experiment_id>
```

Do not edit the generated blocks by hand. Every number in them comes from `metrics.json` and `confidence_intervals.json` of the named experiment.

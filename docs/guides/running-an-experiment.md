# Running an experiment

```bash
python -m app.control_plane.cli experiment run examples/control_plane_demo/experiment.yaml --demo --seed-baseline production
```

Or POST `/api/control-plane/experiments/run` with JSON cases + evaluators.

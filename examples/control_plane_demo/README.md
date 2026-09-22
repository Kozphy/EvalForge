# Control Plane Demo

Deterministic offline demo of the EvalForge Evaluation Control Plane.

## Run

```bash
python -m app.control_plane.cli experiment run examples/control_plane_demo/experiment.yaml --demo --seed-baseline production
```

This uses fake DeepEval and Promptfoo adapters (no paid APIs), then:

1. Loads golden cases from the YAML
2. Runs evaluators via the registry
3. Normalizes results
4. Compares against a seeded baseline
5. Evaluates release policy
6. Emits an audit manifest with evidence hashes

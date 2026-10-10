# Control Plane Upgrade Report

**Version:** 0.4.0  
**Date:** 2026-09-22

## Architecture

EvalForge now exposes an additive **Evaluation Control Plane** under `app/control_plane/`. Existing FastAPI workbench behavior (`heuristic` / `openai` / `client_api` runs, review, import/export) is preserved.

Invariant:

```text
EvalForge owns: orchestration, normalization, baseline, regression,
policy, approval models, evidence, governance

External systems own: specialized evaluation, red teaming, observability
```

## Implemented Components

- Canonical contracts (`EvaluationResult`, `ExperimentSpec`, run/failure/policy enums)
- `EvaluatorRegistry` + adapter protocol
- Adapters: `custom.heuristic`, `deepeval` (optional + fake), `promptfoo` (optional + fake)
- `TraceProvider` + Phoenix optional/fake
- Orchestrator (plan → execute → normalize → evidence → baseline → regression → policy)
- Baseline registry (immutable versions)
- Regression engine + policy engine (`ALLOW/DENY/REVIEW/WARN`)
- Evidence store + redaction + audit manifest hashes
- Human review models
- In-process event bus
- CLI (`python -m app.control_plane.cli`)
- API under `/api/control-plane/*`
- Demo: `examples/control_plane_demo/`
- ADRs 001–008 + architecture docs

## Compatibility

- No breaking change to existing `/api/projects/*/runs` paths
- SQLite workbench schema unchanged for legacy tables
- Control-plane stores start in-memory (API/CLI session scope)

## Test Results

```text
TESTS
PASSING: 53
```

Local command: `pytest -q` (includes legacy workbench + control-plane contract/E2E tests).
Demo CLI verified: `python -m app.control_plane.cli experiment run examples/control_plane_demo/experiment.yaml --demo --seed-baseline production` → `policy_decision: ALLOW`.

## Known Limitations

1. Live DeepEval/Promptfoo are gated; CI uses fakes
2. Control-plane persistence is in-memory (not yet SQLite repositories)
3. Durable retry worker / DLQ not implemented
4. OTEL metrics export not wired
5. Golden dataset immutability still shared with mutable workbench cases
6. Policy/YAML authoring UX is minimal

## Future Work

### P0
- SQLite repositories for experiments/runs/baselines/evidence
- Wire existing review queue to `AWAITING_REVIEW` decisions

### P1
- Live Promptfoo CLI executor with config path
- Live DeepEval metric subset with explicit enable flag
- Dataset snapshot hashing / immutable golden sets

### P2
- OpenTelemetry instrumentation
- Async workers + dead-letter
- Multi-tenant auth

## Production Readiness

| Dimension | Assessment |
|---|---|
| Reliability | **Partial** — sync orchestrator + budget stop; no durable retries |
| Security | **Good start** — redaction pipeline; optional adapters; no secret persistence in evidence |
| Observability | **Partial** — trace provider interface only |
| Auditability | **Good start** — manifest + evidence hashes |
| Extensibility | **Good** — registry/adapters isolated from core |
| Testability | **Good** — fakes + contract + E2E offline path |

```text
TESTS
PASSING: 53

CONTROL_PLANE_READY: PARTIAL

SUPPORTED_BACKENDS:
[custom.heuristic, deepeval(fake/optional), promptfoo(fake/optional), phoenix(fake/optional)]

MAJOR_REMAINING_GAPS:
[durable CP persistence, live provider execution, OTEL, golden immutability]

NEXT_RECOMMENDED_MILESTONE:
Persist control-plane entities in SQLite behind repository interfaces
```

# ADR-002: Canonical Evaluation Contract

## Status
Accepted

## Context
DeepEval, Promptfoo, Phoenix, and first-party graders emit incompatible shapes.

## Decision
Introduce versioned Pydantic models (`EvaluationResult`, `ExperimentSpec`, `EvaluationRun`, …) under `app/control_plane/contracts` as the provider-neutral contract (`schema_version=1.0.0`).

## Consequences
Adapters must normalize into this contract. Forward-compatible JSON serialization is required for audit evidence.

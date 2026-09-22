# ADR-003: Adapter / Plugin Architecture

## Status
Accepted

## Context
Hard-coding providers into the runner prevents extension.

## Decision
Use an `EvaluatorAdapter` protocol plus `EvaluatorRegistry` (`register/list/get/healthcheck`). Optional adapters degrade gracefully when dependencies are absent. Fakes exist for deterministic CI.

## Consequences
New evaluators can be added without changing orchestrator internals.

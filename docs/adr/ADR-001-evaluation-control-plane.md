# ADR-001: Evaluation Control Plane Architecture

## Status
Accepted

## Context
EvalForge began as a self-contained evaluation workbench that implements graders directly. Production AI systems need to orchestrate specialized backends (quality, security, observability) without rewriting them.

## Decision
EvalForge becomes an **Evaluation Control Plane**: it owns orchestration, normalization, baseline, regression, policy, approval, and evidence. External systems own specialized evaluation.

## Consequences
- Core package `app/control_plane/` is additive; existing `execute_run` paths remain.
- Third-party tools integrate via adapters, not core imports.

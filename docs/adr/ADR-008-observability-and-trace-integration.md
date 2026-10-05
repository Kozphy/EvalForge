# ADR-008: Observability and Trace Integration

## Status
Accepted

## Context
Evaluation decisions need linkage to runtime traces without coupling the domain model to Phoenix.

## Decision
Introduce a `TraceProvider` protocol. Phoenix is one optional implementation; fakes support CI.

## Consequences
Core contracts store `trace_id` only; span details remain provider-specific payloads.

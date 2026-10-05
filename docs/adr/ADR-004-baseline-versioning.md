# ADR-004: Baseline Versioning

## Status
Accepted

## Context
Release decisions require immutable historical baselines.

## Decision
Baselines are append-only versioned records. Promotion creates a new version and deactivates prior active versions without mutating historical payloads.

## Consequences
Rollback changes the active pointer; it does not rewrite metrics history.

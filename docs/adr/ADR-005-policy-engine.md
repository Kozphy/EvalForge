# ADR-005: Policy Engine

## Status
Accepted

## Context
Boolean pass/fail is insufficient for release governance.

## Decision
Policy decisions return `ALLOW | DENY | REVIEW | WARN` with rule ID, version, matched evidence, and timestamps.

## Consequences
Human review can be triggered by `REVIEW` without collapsing into deny/allow.

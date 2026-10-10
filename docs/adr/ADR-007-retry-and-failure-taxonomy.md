# ADR-007: Retry and Failure Taxonomy

## Status
Accepted

## Context
Inconsistent error naming blocks safe retries.

## Decision
Formal `FailureClass` enum distinguishes retryable provider/network/timeout failures from non-retryable configuration, policy, and schema failures.

## Consequences
Orchestrator and adapters share one taxonomy; durable run states include PARTIAL and BUDGET_EXCEEDED.

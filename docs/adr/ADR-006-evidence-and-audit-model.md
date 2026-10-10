# ADR-006: Evidence and Audit Model

## Status
Accepted

## Context
Auditors need reproducible, redacted artifacts.

## Decision
Append-only evidence records with SHA-256 hashes; audit manifests summarize experiment/baseline/policy/approvals. A redaction pipeline strips secrets before persistence.

## Consequences
Evidence never stores API keys, auth headers, or credential material.

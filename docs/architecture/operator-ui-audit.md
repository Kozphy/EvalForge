# Operator UI Audit (pre-implementation)

**Date:** 2026-09-22 · **App:** EvalForge 0.4.0 → **post:** 0.5.0 operator console · **CI:** 59 pytest passed (post)

## Implementation truth

- Control plane **implemented** in `app/control_plane/` (orchestrator, baseline, regression, policy, evidence, adapters).
- HTTP: `/api/control-plane/experiments/run`, evaluators, runs, baselines, evidence.
- Workbench SQLite UI exists at `/workbench`; operator console at `/` consumes `/api/operator/*`.
- CP stores remain **in-memory** (not durable). Approvals are **prototype**.

## Strongest evidence

- `tests/test_control_plane.py` E2E offline path (SUCCEEDED + ALLOW + manifest hash)
- `tests/test_operator_ui.py` coherent REVIEW→PENDING journey + self-approve guard
- CLI demo + CI smoke + `scripts/check_operator_console.py`

## Maturity (pre-UI)

| Dimension | Rating |
|---|---|
| Product UX (CP) | none → see deliverables for post |
| Software engineering | solid |
| AI evaluation | partial |
| Governance | partial |
| Reliability | early |
| Production evidence | early |

## Three highest-value usability gaps

1. No release-decision surface (policy/regression/manifest unused by UI) — **addressed in v0.5 console**
2. No operator journey across Run → Regression → Policy → Evidence → Approval → Audit — **addressed via demo_fixture**
3. Ephemeral CP memory vs durable workbench SQLite — **still open; labeled explicitly**

## Frontend approach

Extend **existing vanilla** `app/static/` into an enterprise operator console. No new SPA framework. Mark fixture-backed modules as **demo_fixture** / **prototype**.

Post-implementation: [`operator-ui-deliverables.md`](operator-ui-deliverables.md)

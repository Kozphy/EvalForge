# Operator UI Deliverables (v0.5.0)

**Date:** 2026-09-22  
**Pre-audit:** [`operator-ui-audit.md`](operator-ui-audit.md)

## 1. Repository audit (summary)

| Area | Truth |
|---|---|
| Backend CP | Implemented: orchestrator, baseline, regression, policy, evidence, audit manifests |
| Workbench | Implemented SQLite product at `/workbench` |
| Pre-UI CP surface | APIs existed; **no** operator console consumed them |
| Frontend stack | Extended existing vanilla JS (no React/Next introduced) |
| CI (pre) | pytest + CP CLI smoke + research analysis |

## 2. Usability gap assessment (addressed)

| Gap | Response |
|---|---|
| No release-decision surface | Overview release-readiness card + run detail chain |
| No Run→…→Audit journey | Coherent `demo_fixture` IDs across all modules |
| Ephemeral CP vs durable workbench | Explicit maturity labels; live overlay when CP data exists |

## 3. Proposed / shipped architecture

```
app/static/index.html|operator.js|operator.css   # operator console
app/control_plane/operator_fixtures.py           # coherent demo world
app/control_plane/operator_service.py            # adapters + prototype approval
app/main.py                                      # /api/operator/*
scripts/check_operator_console.py                # CI static+HTTP smoke
tests/test_operator_ui.py                        # decision-path tests
```

## 4. Implemented UI

Primary nav (non-empty; maturity labeled where needed):

Overview · Evaluation Runs · Baselines · Regressions · Policy Gates · Evidence · Approvals (prototype) · Audit Log · Research / Benchmarks · Settings

Run detail includes: summary, metric comparison, regression analysis, policy decision + timeline, evidence, final release gate chain.

## 5. Backend / API changes

- Added `/api/operator/*` read APIs + prototype approval POST + demo reset.
- Preserved `/api/control-plane/*` and workbench routes.
- No unnecessary CP domain redesign.

## 6. Tests

- `tests/test_operator_ui.py` — overview, chain, evidence, approval guard, empty/404, HTML serve.
- Full suite: **59 passed** (local).

## 7. CI changes

- `python scripts/check_operator_console.py` after pytest (static nav/symbols + HTTP smoke).
- Existing backend/CP/research steps retained.

## 8. Screenshots / demo assets

- `docs/assets/operator-console-overview.png`
- `docs/assets/operator-console-run-detail.png`
- Banner retained: `docs/assets/evalforge-banner.jpg`.

## 9. README

Updated to lead with control-plane positioning, lifecycle, demo scenario, maturity table, limitations.

## 10. Limitations

See README. Key: fixture KPIs, in-memory CP, prototype approvals, no immutable audit claim, read-only baseline promote.

## 11. Remaining Staff-level gaps

1. Durable CP repositories + real authZ for approvals  
2. Wire operator UI exclusively to live CP (reduce fixture dependency)  
3. Operational SLOs, multi-tenant tenancy, signed evidence  
4. E2E browser automation (Playwright) beyond HTTP path tests  
5. Production adoption evidence (none today — correctly unlabeled)

## Final maturity assessment

| Dimension | Rating |
|---|---|
| Product UX maturity | Partial (credible operator demo; not productized SaaS) |
| Software engineering maturity | Solid |
| AI evaluation maturity | Partial |
| Governance maturity | Partial / prototype on human gate |
| Reliability maturity | Early |
| Production evidence maturity | Early |

**Staff-level credibility note:** Architecture and inspectable decision UX are present; durable ops evidence and production adoption are not. Do not award Staff-level maturity solely on structure.

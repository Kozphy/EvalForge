# Finance Evaluation Portfolio Audit (Phase 1)

**Date:** 2026-09-24 · **Repo version:** 0.5.0 · **Auditor stance:** Staff-level, non-inflating

## 1. Implementation truth

| Capability | Reality |
|---|---|
| Workbench (SQLite) | **Real** — projects, docs, cases, runs, review, export |
| Deterministic graders | **Real** — format/rules/JSON/citations; Python/SQL = **syntax only** |
| Optional OpenAI judge | **Real code path**; not required for CI |
| Control plane engines | **Real in-process** — baseline, regression, policy, evidence hashes |
| Operator console | **Fixture-backed demo** (customer-support journey) |
| Finance/accounting depth | **Toy** — ~3 seed cases (depreciation) |
| Executable finance SQL/Python grading | **Missing** |
| Durable CP audit store | **Missing** (in-memory) |
| Research paper results | **Scaffold** — no filled quantitative claims |

## 2. Strongest existing evidence

1. `tests/test_control_plane.py` — offline CP path: normalize → baseline → regression → policy → evidence
2. `tests/test_graders.py` — deterministic rule library
3. `tests/test_review.py` — durable human review + disagreement
4. `tests/test_operator_ui.py` — inspectable REVIEW → PENDING journey
5. CI: pytest + operator smoke + CP CLI + research metrics (`ci.yml`)

## 3. Current maturity

**Overall: MVP**

| Subsystem | Maturity |
|---|---|
| Evaluation engineering shell | MVP |
| Operator / governance UX | Prototype → MVP |
| Finance/accounting eval | **Prototype** |
| Coding eval (exec) | Prototype |
| Production ops evidence | Prototype |

Not Portfolio-ready for Finance AI Evaluator roles until a versioned finance golden set + measurable offline results exist.

## 4. Unsupported / overstated claims

- Leading portfolio narrative as “Finance AI” while default operator demo is **customer-support metrics**
- Architecture diagrams implying DeepEval/Promptfoo/Phoenix depth (optional/fakes)
- SQL/Python graders implying correctness grading (syntax-only today)
- Research/Benchmarks UI implying completed study (surfaces assets only)
- `docs/architecture/current-state.md` stale (still describes CP as missing)

## 5. Three highest-value credibility gaps

1. **Versioned finance/accounting golden set** with rubrics, tolerances, and known failure modes (≥100 items)
2. **Reproducible offline pipeline** producing measurable metrics, taxonomy-tagged failures, policy decision, and hashed evidence — without API keys
3. **Executable coding path** for finance SQL/Python (result checks), not syntax flags alone

## Gap analysis summary

| Area | Real | Partial | Docs-only | Missing | Provable today |
|---|---|---|---|---|---|
| Eval workbench | ✓ | | | | seed→run→metrics |
| LLM judge | | ✓ optional | | | code path exists |
| Human review | ✓ workbench | ✓ operator prototype | | durable CP approvals | disagreement tests |
| CP policy/regression | ✓ engines | in-memory | | durable store | offline e2e test |
| Finance benchmark | | 3 cases | | suite | import of accounting JSONL |
| Coding correctness | | syntax | | sandboxed exec | syntax tests |
| Audit evidence | ✓ hashes | | | append-only durable | manifest in CP test |

## Claims that can currently be proven

- Deterministic grading + human review state machine works
- Control-plane decision chain is inspectable in tests and demo fixtures
- Secrets can be redacted from client-API paths
- Binary classification metrics + bootstrap CI code exists (toy data)

## Claims that cannot currently be proven

- Credible Finance AI evaluation depth *(addressed in v0.6 `finance_eval/` — see after)*
- Production governance durability
- Judge–human agreement on finance tasks *(partial: seeded n=20 agreement 0.95)*
- Coding evaluator readiness for finance analytics *(partial: result fixtures)*

---

## After finance vertical (v0.6.x)

| | Before | After |
|---|---|---|
| Overall maturity | MVP | **MVP → Portfolio-ready (finance eval slice)** |
| Finance/accounting eval | Prototype | **Portfolio-ready** (154-case golden + pipeline) |
| Live model runner | Missing | **Implemented** (cost/latency/retry capped) |
| Coding eval | Prototype | Partial (result fixtures, no sandbox) |
| Governance evidence | Prototype | Partial (file manifests + policy tests) |

### P0 gaps (resolved / remaining)

| Gap | Status |
|---|---|
| Live multi-model runner + cost/latency | **Resolved** in `finance_eval/live.py` |
| Independent LLM judge | Still open (judge remains simulated) |
| SQL/Python sandbox | Still open |

### Measurable offline results

- Gold baseline accuracy: **100%** · Policy **PASS**
- Candidate fixture accuracy: **79.9%** · Critical error rate **5.2%** · Policy **FAIL**
- Live runner: OpenAI/Anthropic/mock with cost cap, retries, latency/tokens; CI uses `--provider mock`
- Tests: **71** passed (includes `tests/test_finance_eval.py` + `tests/test_finance_live.py`)

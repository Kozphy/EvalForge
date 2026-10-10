# EvalForge Current State Assessment

**Date:** 2026-09-22  
**App version assessed:** 0.3.0  
**Purpose:** Baseline for upgrading EvalForge into an Evaluation Control Plane.

---

## 1. Current architecture

EvalForge is a **local-first evaluation workbench**, not a multi-backend control plane.

```text
UI (vanilla JS)
      │
FastAPI (app/main.py)
      │
service.execute_run ──► client_api (optional SUT invoke)
      │                 retrieval (TF-IDF)
      │                 graders (rules / heuristic / OpenAI)
      ▼
SQLite (projects, documents, eval_cases, runs, results, review_decisions)
      │
export + human review queue
```

| Layer | Implementation |
|---|---|
| API | FastAPI routes in `app/main.py` |
| Domain | Projects → documents/cases → runs → results → reviews |
| Graders | Deterministic rules + heuristic claims + optional OpenAI structured judge |
| SUT invoker | v0.3 `client_api` POST runner (`{{prompt}}`, field path, env-var auth name) |
| Storage | SQLite + non-destructive `migrate_schema()` |
| Research | Separate `research/` metrics and manuscript scaffolds |
| UI | `app/static/` vanilla JS |

Providers today: `heuristic` | `openai` | `client_api`.

---

## 2. Existing strengths

1. **Clear product loop** — cases, evidence docs, runs, metrics, export, human review.
2. **Deterministic-first philosophy** — rules never call an LLM; unsupported ≠ false.
3. **Immutable run config snapshots** — `GraderConfig` with git SHA / app version.
4. **Human review state machine** — PENDING → REVIEWED → DISAGREEMENT → ADJUDICATED.
5. **Client API runner** — batch SUT calls with secret redaction and partial failure.
6. **Import/export** — CSV/JSONL import; JSON/JSONL/CSV export with filters.
7. **Test harness** — ~46 pytest cases covering graders, import, review, client API, research.
8. **Honest limitations** — README positions EvalForge as an engineering workbench, not an oracle.

---

## 3. Technical debt

1. **Monolithic runner** — `execute_run` owns planning, execution, persistence, and grading.
2. **No plugin boundary** — third-party evaluators cannot be registered without core edits.
3. **Mutable cases** — client API updates `eval_cases.response` in place (breaks golden immutability).
4. **Dual contracts** — product labels (`no_issue`/`minor`/`major`) vs research `pass`/`fail`.
5. **Unused config knobs** — `evidence_threshold` stored but not applied in heuristic grading.
6. **Sync-only jobs** — no durable run state machine beyond `running`/`completed`/`failed`.
7. **No ADRs / architecture docs** — README is the sole product architecture source.
8. **No product CLI** — only Makefile + research analysis module.
9. **CI is smoke-only** — pytest + research analysis; no lint/type/regression gates.

---

## 4. Missing pieces for Evaluation Control Plane

| Capability | Status |
|---|---|
| Canonical multi-backend evaluation contract | Missing |
| Evaluator adapter protocol + registry | Missing |
| DeepEval / Promptfoo / Phoenix adapters | Missing |
| Experiment first-class entity | Missing |
| Orchestrator (plan → execute → normalize → decide) | Missing |
| Durable run states + retry taxonomy | Missing |
| Baseline registry (immutable versions) | Missing |
| Regression engine | Missing |
| Policy engine (ALLOW/DENY/REVIEW/WARN) | Missing |
| Append-only evidence store + redaction pipeline | Missing |
| Audit manifest + integrity hashes | Missing |
| Evaluation budget controls | Missing |
| Control-plane CLI / API | Missing |
| Domain events | Missing |
| Repository interfaces over persistence | Partial (direct SQL) |
| Golden dataset versioning | Missing |
| Adapter contract tests | Missing |

---

## 5. Components that should be preserved

- Existing FastAPI product API and UI behavior for heuristic/openai/client_api runs
- `RequirementSpec` rule library and `heuristic_grade` / `openai_grade`
- Review workflow and export/import services
- SQLite + non-destructive migrations
- Client API runner and secret redaction helpers
- Research package (orthogonal experimental track)
- Existing pytest suite as regression baseline

---

## 6. Components that should be refactored

- `execute_run` — become one backend path invoked *by* the orchestrator, not the only path
- Run status model — expand toward durable control-plane states without breaking old clients
- Result storage — keep current `results` rows; add parallel normalized evidence / evaluation_result records
- Config snapshots — extend to record evaluator adapter versions and experiment IDs

---

## 7. Components that should be added

1. `app/control_plane/` package (contracts, adapters, orchestration, policy, regression, evidence)
2. Optional adapters: DeepEval, Promptfoo, Phoenix (graceful absent-deps)
3. Fake adapters for deterministic CI demos
4. Experiment YAML schema + CLI
5. Baseline / regression / policy engines
6. Evidence store + audit manifest
7. ADRs and architecture guides
8. Example `examples/control_plane_demo/`
9. Contract + integration tests for the control-plane path

---

## Architectural invariant (target)

```text
EvalForge owns: orchestration, normalization, baseline, regression,
                policy, approval, evidence, governance

External systems own: specialized evaluation, red teaming,
                      observability, provider-specific functionality
```

Existing graders remain a **first-party custom adapter**, not the only evaluation path.

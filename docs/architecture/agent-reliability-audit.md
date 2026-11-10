# Agent Reliability Platform — Phase 1 inventory

**Scope:** EvalForge repository audit before integrating a versioned bridge to
[`Kozphy/ci-failure-orchestrator`](https://github.com/Kozphy/ci-failure-orchestrator)
without merging the repositories.

**Audit base:** `origin/main` @ `4fcec3b` (feature branch cut from this commit).  
**Data labels:** everything below is **local / synthetic** unless marked otherwise.

## Verified (code + tests exist)

| Capability | Path evidence |
|---|---|
| Finance golden set (154) + sha256 manifest | `finance_eval/dataset/` |
| Deterministic graders + `FIN-*` taxonomy | `finance_eval/graders.py`, `taxonomy.py` |
| Offline runner, metrics, bootstrap CI | `finance_eval/runner.py`, `metrics.py` |
| Run-level policy PASS/WARN/FAIL/HUMAN_REVIEW | `finance_eval/policy.py` |
| File evidence manifests | `finance_eval/evidence.py` |
| Live OpenAI/Anthropic clients with cost cap | `finance_eval/live.py` (mock-tested; no committed live results) |
| Workbench API + SQLite | `app/main.py`, `app/db.py` |
| Control plane contracts / adapters (in-memory) | `app/control_plane/` |
| Knowledge-distillation research scaffold | `research/distillation.py`, `tests/test_distillation.py` |
| CI: pytest on Python 3.11/3.12 | `.github/workflows/ci.yml` |

## Simulated / curated (honest labels in code)

| Component | Label | Path |
|---|---|---|
| LLM-as-judge | `simulated_heuristic_judge` | `finance_eval/judge.py` |
| Human reviews | `curated_seed` | `finance_eval/human_review.py` |
| Operator console journey | fixture demo | `app/control_plane/operator_fixtures.py` |
| Mock live provider | synthetic latency/tokens | `finance_eval/live.py` |

## README / portfolio claims vs evidence

| Claim | Status |
|---|---|
| Offline candidate accuracy ~79.9%, policy FAIL | **Measured** on synthetic fixture (`docs/reports/finance-evaluation-report.md`) |
| “71 pytest” | **Stale count** — treat as moving; verify with `pytest -q` |
| Live multi-model evaluation | **Implemented clients**; **no** recorded real-provider run |
| SQL/Python evaluation | Numeric string checks — **not** sandboxed execution |
| Production readiness / customers | **Not claimed** in portfolio ledger; do not invent |

## Security / evaluation boundaries

| Gap | Detail |
|---|---|
| Workbench API auth | Mutating routes in `app/main.py` have no authn |
| Dataset integrity gate | Hash recorded; fail-closed verify may be incomplete on this base commit |
| No held-out finance split | All cases `split: "test"` |
| No merge with ci-failure-orchestrator | Separate repo; this work adds a **versioned interface only** |

## Dependencies (runtime)

From `requirements.txt`: FastAPI, uvicorn, pydantic, scikit-learn, openai, httpx, PyYAML, pytest, jsonschema, python-multipart.  
**Not** a dependency: `ci-failure-orchestrator` (intentionally — repos stay separate).

## Interfaces usable for a bridge

| System | Decision vocabulary | Evidence style |
|---|---|---|
| EvalForge finance | PASS / WARN / FAIL / HUMAN_REVIEW_REQUIRED | sha256 manifests, redaction helpers |
| EvalForge control plane | ALLOW / DENY / REVIEW / WARN | `app/control_plane/contracts` |
| ci-failure-orchestrator | APPROVE / REJECT / ESCALATE | policy gate + append-only audit |

**Bridge vocabulary (this feature):** `PASS` / `WARN` / `BLOCK` with explicit mapping documented in `agent_reliability/interface_v1.py`.

## Out of scope for this change

- Merging repositories or vendoring CFO source
- Automatic merge/deploy
- Paid API calls or GPU benchmarking claims
- Production deployment

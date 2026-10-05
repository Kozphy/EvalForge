# Portfolio positioning

What EvalForge is, what it can honestly be used to claim, and what it cannot.
Every claim links to something a reviewer can run or read. Last verified 2026-09-24
at commit `76b8fde` (see [`end-to-end-flow.md`](end-to-end-flow.md)).

## One-sentence positioning

EvalForge is a **deterministic-first release gate for LLM outputs on finance & accounting
tasks**: a frozen, hashed golden set is graded by rule-based checkers, compared to a
baseline, and turned into a PASS/WARN/FAIL decision with an auditable evidence bundle.

It is a **single-author portfolio project**. It has no production deployment, no external
users, and no real-model benchmark results.

## Data-provenance labels used in this repo

| Label | Meaning here | Where it applies |
|-------|-------------|------------------|
| **production** | Real traffic / real users | **Nothing in this repo.** |
| **production-like** | Real provider or realistic load, controlled setting | **Nothing yet.** |
| **local benchmark** | Measured by running repo code locally or in CI | `finance_eval` gold/candidate/mock-live runs, pytest |
| **synthetic** | Data authored in this repo | `finance-accounting-v1` (154 cases, planted errors), operator-console fixtures, `research/example_predictions.csv` (6 rows) |
| **simulated** | A component that stands in for a real one | LLM judge (`judge.py`), seeded human reviews (`human_review.py`), `mock` provider latency |

## Claim ledger

### Implemented — code exists, is tested, runs in CI

| Capability | Evidence |
|------------|----------|
| Versioned golden set, sha256-pinned, LF-pinned | `finance_eval/dataset/MANIFEST.json`, `.gitattributes` |
| 6 deterministic grader modes + `FIN-*` failure taxonomy | `finance_eval/graders.py`, `taxonomy.py`, `tests/test_finance_eval.py` |
| Metrics with bootstrap 95% CI | `finance_eval/metrics.py` |
| Baseline regression + policy gate (`FIN-POL-001..005`) | `finance_eval/policy.py` |
| Append-only evidence with sha256 manifests | `finance_eval/evidence.py` (hashes independently re-verified, see E2E doc) |
| Live runner with cost cap, retry budget, timeout, redacted summary | `finance_eval/live.py`, `tests/test_finance_live.py` (6 tests; provider HTTP via `httpx.MockTransport`) |
| Local SQLite workbench: import (CSV/JSONL), review queue, export, remote client-API target | `app/`, `tests/test_import.py` (10), `test_client_api.py` (11), `test_review.py`, `test_export.py` |
| Control-plane orchestration / baseline / policy / evidence (**in-memory stores**) | `app/control_plane/`, `tests/test_control_plane*.py` (7) |
| CI: pytest + console smoke + CP demo + finance smoke on Python 3.11/3.12 | `.github/workflows/ci.yml` |

### Measured — numbers produced by running the code (local benchmark, synthetic data)

| Measurement | Value | Caveat |
|-------------|-------|--------|
| Gold baseline accuracy | 154/154 | Oracle responses; proves graders accept correct answers |
| Offline candidate accuracy | 0.799, 95% CI [0.740, 0.857] | Candidate is a fixture with planted errors, not a model |
| Candidate critical error rate → policy | 0.052 → **FAIL** | Threshold 0.05 is illustrative |
| Grader catches planted errors | 31/31 valid planted cases, 0 false alarms on 122 clean | Same author wrote errors and graders; one case (`PY-015`) is defective |
| Taxonomy attribution vs planted code | 24/31 | Grader labels the symptom (wrong number), not always the concept |
| Test suite | 71 passed | Count, not coverage |

### Demonstrated — shown working end-to-end, but not measured against anything real

- Full gold → candidate → mock-live → report flow, reproducible from a clean clone in seconds.
- Policy gate blocking a regressed candidate with named rules and observed values.
- Cost cap stopping a live run mid-batch (`CostCapExceeded`, covered by test).
- Operator console journey at `/` (customer-support **fixture**, unrelated to finance data).

### Experimental / scaffold

- `paper/manuscript.md` — explicitly a scaffold; contains no results.
- `research/` — analysis script over 6 example prediction rows.
- LLM-as-judge — `judge.py` mirrors the deterministic result; it is a pipeline slot, not a judge.

### Not yet proven — plausible but no evidence in this repo

| Claim someone might assume | Why it is not proven |
|----------------------------|----------------------|
| "Evaluates real models" | No recorded run against OpenAI/Anthropic; only mock + MockTransport |
| "Judge–human agreement 0.95" | **Constructed:** both sides copy the deterministic result; one disagreement is forced in code. Removed from README headline. |
| Precision/recall/F1 in reports | **Tautological** (compares `passed` to itself); always 1.0. Open defect. |
| Grader validity on unseen responses | Graders were only tested on responses from the same author |
| Durable, tamper-evident audit trail | Evidence is plain files; control-plane evidence is in-memory |
| Observability (structured logs, correlation IDs, metrics) | Not implemented |
| Safe code evaluation | SQL/Python cases compare stated results; no sandboxed execution |
| Scale / performance | No load or latency benchmarks exist |

### Planned (next, in order)

1. Replace tautological precision/recall with grader-vs-planted detection metrics.
2. Runner verifies dataset sha256 against `MANIFEST.json` before grading (fail closed).
3. Benchmark harness with fixtures only (`benchmarks/`), no invented numbers.
4. Failure evidence directory and failure taxonomy write-up.
5. One real-provider run under a hard cost cap, recorded as **production-like**, only if API
   access is available.

## Target roles and honest fit

| Role | Fit | Strongest verifiable artifact | Main gap |
|------|-----|-------------------------------|----------|
| LLM Evaluation Engineer | Strong for portfolio | Deterministic graders + policy gate + hashed evidence, CI-reproducible | No real-model results |
| Finance AI Evaluator | Strong for portfolio | 154-case taxonomy-labelled golden set + report | Synthetic cases, single author, no domain reviewer |
| AI Governance / Risk | Partial | Named policy rules with observed values in every decision | No durable audit store, no real human review |
| Coding Evaluator | Weak–partial | SQL/Python result checks | No execution sandbox |
| Senior/Staff *platform* engineer | **Not supported yet** | — | No production use, no observability, no scale evidence, no cross-team impact |

## What a reviewer can verify in ~10 minutes

```bash
pip install -r requirements.txt
pytest -q                                   # expect 71 passed
python -m finance_eval run --mode gold --write-baseline
python -m finance_eval run --mode candidate # expect accuracy ~0.799, policy FAIL
```

Then open `finance_eval/output/evidence/<run_id>.manifest.json` and re-hash the
results file yourself.

## Claims this repo deliberately does not make

- No production readiness, users, customers, incidents, or SLAs.
- No Staff-level organisational impact.
- No measured LLM judge quality and no real human-review agreement.
- No comparison between real models.

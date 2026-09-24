# End-to-end flow: finance release gate (verified)

This document traces **one** workflow through the codebase and records what happened
when it was actually run. It is the flow a reviewer should reproduce first.

> **Data label:** every number below is a **local benchmark** on a **synthetic** dataset
> (`finance-accounting-v1`, authored in this repo). No production traffic, no real users,
> no real model provider was involved.

## The question this flow answers

*"Should candidate model/prompt X be allowed to ship for finance & accounting tasks,
given a frozen golden set and a gold baseline?"*

## Stages and where they live

| # | Stage | Code | Output |
|---|-------|------|--------|
| 1 | Load frozen dataset (154 cases, sha256-pinned) | `finance_eval/dataset/`, `schema.py` | `FinanceCase` objects |
| 2 | Produce responses (gold / offline candidate / live client) | `runner.py` (`gold_candidate`, `offline_candidate`), `live.py` | response per case |
| 3 | Deterministic grading (numeric, exact_text, contains_all, journal_json, sql_result, python_result) | `graders.py` | pass/fail + `FIN-*` failure codes |
| 4 | Simulated judge (mirrors stage 3; never overrides it) | `judge.py` | rubric dict, labelled `simulated_heuristic_judge` |
| 5 | Metrics + bootstrap 95% CI | `metrics.py` | `accuracy`, `critical_error_rate`, per-class rates |
| 6 | Regression vs gold baseline | `policy.py::compare_to_baseline` | per-metric delta + severity |
| 7 | Policy gate (`FIN-POL-001..005`) | `policy.py::evaluate_policy` | `PASS` / `WARN` / `FAIL` / `HUMAN_REVIEW_REQUIRED` |
| 8 | Evidence (append-only files, sha256) | `evidence.py` | `<run_id>.manifest.json`, `<run_id>.results.jsonl`, `evidence_index.jsonl` |
| 9 | Report / redacted live summary | `report.py`, `live.py::write_redacted_live_summary` | `docs/reports/finance-evaluation-report.md`, `baselines/live_run_summary.example.json` |

## Reproduce

Same commands CI runs (`.github/workflows/ci.yml`, "Finance evaluation smoke"):

```bash
python -m finance_eval run --mode gold --write-baseline
python -m finance_eval run --mode candidate
python -m finance_eval run --mode live --provider mock --limit 5 --max-cost-usd 1
python -m finance_eval report
pytest -q
```

## Verification run — 2026-09-24

Environment: Windows 11, Python 3.11.9, commit `76b8fde`. Each step exited `0` and took
~0.2 s wall-clock (deterministic, no network).

| Step | Cases | Passed | Accuracy (95% CI) | Critical error rate | Policy |
|------|------:|-------:|-------------------|--------------------:|--------|
| gold (`--write-baseline`) | 154 | 154 | 1.000 [1.000, 1.000] | 0.000 | PASS |
| candidate (offline fixture) | 154 | 123 | 0.799 [0.740, 0.857] | 0.052 | **FAIL** |
| live, provider=`mock`, limit 5 | 5 | 5 | 1.000 | 0.000 | PASS |

Candidate `FAIL` came from two rules:

- `FIN-POL-001` — `critical_error_rate > 0.05` (observed 0.0519)
- `FIN-POL-004` — critical regression on `critical_error_rate` (baseline 0.0 → 0.0519)

Mock live run: 120 tokens, estimated cost $0.000012 against a $1.00 cap (`max_retries=2`;
retries actually used are not recorded in the summary). Latency (12 ms) is a constant
returned by the mock client, **not** a measurement.

`pytest -q`: **71 passed**.

### Evidence integrity check (done independently of the code under test)

Recomputed with `hashlib` outside `evidence.py`:

- `finrun_15d42bb4b7d1.results.jsonl` sha256 == `artifact_hashes.results_jsonl_sha256` in its manifest ✔
- dataset file sha256 == `dataset/MANIFEST.json` == `dataset_sha256` recorded in the manifest ✔
  (`d6d2ede08b0ca6eecd040c3e6e54ba4337e7cae14e67ec196c8fb4d008a4c80f`)

### Grader vs planted failures (measured during this verification)

The offline candidate has errors deliberately planted per case (`planted_failure`).
Scoring the deterministic grader against those labels:

| | Grader: fail | Grader: pass |
|---|---:|---:|
| **Planted error** (32 labelled) | 31 | 1 |
| **No planted error** (122) | 0 | 122 |

- Catch rate 31/32; no false alarms.
- The single "miss", `PY-015`, is a **dataset defect**, not a grader miss: its golden
  value is `1.0` for a non-computable expression and the "wrong" candidate answer is `1`,
  which equals the golden. Effective planted failures: **31**, all caught.
- Taxonomy attribution: the planted code appears in the grader's codes for **24/31** caught
  cases. Mismatches are mostly `FIN-ACC-002` (planted) vs `FIN-CALC-001` (assigned) on
  equity cases — the grader sees a wrong number, not the accounting concept behind it.

Caveat: the same author wrote the planted errors and the graders, so this is a
consistency check, not an independent validation.

## Defects found by this verification

| Defect | Impact | Status |
|--------|--------|--------|
| `precision`/`recall`/`f1`/`false_positive_rate` in `metrics.py` compare `r.passed` to itself | Always 1.0 / 1.0 / 1.0 / 0.0 for any run — carries no information but appears in the report JSON | **Open.** Proposed: replace with grader-vs-`planted_failure` detection metrics (above) in candidate mode, `null` otherwise. |
| Judge–human agreement 0.95 is constructed: judge mirrors deterministic result; seeded "human" rows mirror it too except one disagreement forced in `human_review.py` | Number is determined by the seeding code, not by any judgment | README headline corrected; code **open** (needs real reviews or removal). |
| `PY-015` golden/candidate are both `1` | Planted-failure count overstated by 1 | **Open.** Fixing changes the dataset sha256 → requires a `v1.1` dataset bump, not an in-place edit. |
| `core.autocrlf=true` checkout converted dataset to CRLF → recorded sha256 would diverge from `MANIFEST.json` silently | Reproducibility | **Fixed** in `76b8fde` (`.gitattributes` `eol=lf`). Runner still does not *verify* the hash — open. |
| Running the flow rewrites tracked files (`docs/reports/finance-evaluation-report.md`, `baselines/live_run_summary.example.json`) and tests regenerate `dataset/*.jsonl` | Noisy diffs; tests mutate versioned data | Open. |
| `evidence_index.jsonl` stores absolute, machine-specific paths | Evidence bundle not relocatable | Open. |

## What this flow does **not** prove

- Behaviour of any real model: the candidate is a fixture with planted errors, and the live
  path was exercised only with the `mock` provider. OpenAI/Anthropic clients are covered by
  `httpx.MockTransport` tests, never by a recorded real call.
- That the policy thresholds (e.g. 5% critical error rate) are the *right* thresholds for
  any real finance workflow — they are illustrative.
- Human review quality — there are no real human reviews.
- Anything about the operator console / control plane (`app/`), which uses a separate
  customer-support fixture and in-memory stores.

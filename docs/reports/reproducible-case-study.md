# Reproducible case study: baseline, candidate, evaluation, regression, policy decision, audit evidence

This walkthrough uses only the synthetic `finance-accounting-v1` dataset and offline fixtures. It makes no live-model claim. The command sequence was run on 2026-11-10 (Asia/Taipei) at commit `4fcec3bc4fa816a533d3445ebc3dc82d38871659` with Python 3.12.15 on Linux, with no API keys set. The numbers below are what that run printed. Random run IDs and timestamps will differ when you rerun it, but the metrics should not.

**Rerun with fixes, 2026-11-11 (Asia/Taipei).** The same sequence was rerun on that commit plus local, uncommitted fixes for three defects: the precision, recall, and F1 metrics, the dataset manifest check, and the mock run that rewrote a tracked file. Every pass count, error rate, policy decision, and evidence hash stayed the same. Only the precision, recall, F1, and false-positive values changed, and the tamper check now stops the run. The tables below show both runs where they differ.

## Scenario

A finance team wants to know whether a new model version (the *candidate*) may replace the current one for answering accounting and financial-analysis questions. The release rule says a candidate with more than 5% critical accounting errors, or a critical regression against the approved baseline, must not ship.

- **Baseline:** The `gold` mode, which answers every case with the expected answer. It is an oracle, not a real model.
- **Candidate:** The `candidate` mode, a committed offline fixture with planted errors. It is not a real model either.

## Command sequence

Run these from the repository root in a virtual environment. Baseline and evidence go to a temporary directory so that tracked files are not overwritten.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
unset OPENAI_API_KEY ANTHROPIC_API_KEY                 # offline only

# 0. Dataset integrity (the runner now enforces this too; the manual check stays useful)
python -m finance_eval generate-dataset
sha256sum finance_eval/dataset/finance_accounting_v1.jsonl
grep '"sha256"' finance_eval/dataset/MANIFEST.json

# 1. Baseline
python -m finance_eval run --mode gold --write-baseline \
  --baseline /tmp/cs/baseline.json --evidence-dir /tmp/cs/ev-baseline

# 2. Candidate + evaluation + regression + policy
python -m finance_eval run --mode candidate \
  --baseline /tmp/cs/baseline.json --evidence-dir /tmp/cs/ev-candidate

# 3. Audit evidence
sha256sum /tmp/cs/ev-candidate/*.results.jsonl
cat /tmp/cs/ev-candidate/*.manifest.json

# 4. Test suite
pytest -q
```

## Results from the recorded run

| Step | What was observed |
|---|---|
| 0. Dataset | 154 cases. The sha256 is `d6d2ede08b0ca6eecd040c3e6e54ba4337e7cae14e67ec196c8fb4d008a4c80f`, both after regeneration and in `MANIFEST.json`. 32 cases carry a planted failure |
| 1. Baseline | 154 of 154 pass. Policy `PASS`. The baseline file records the dataset version, the dataset sha256, and `model: oracle-expected-answer` |
| 2. Evaluation | 123 of 154 pass (accuracy 0.7987, bootstrap 95% CI 0.740–0.857). Critical error rate 0.0519. Calculation error rate 0.0519. These values were identical in both runs |
| 2. Precision, recall, F1 | First run: 1.0, 1.0, and 1.0, which was tautological. Rerun with fixes: precision 0.9919 (122/123), recall 1.0 (122/122), F1 0.9959, false-positive rate 0.03125 (1/32). Gold baseline: 1.0, 1.0, and 1.0, with no false-positive rate |
| 2. Regression | `critical_error_rate` went from 0.0 to 0.0519 (delta +0.0519, severity critical) |
| 2. Policy decision | **`FAIL`**. Matched `FIN-POL-001` (`critical_error_rate > 0.05`) and `FIN-POL-004` (critical regression) |
| 3. Audit evidence | `finrun_<id>.results.jsonl`, `finrun_<id>.manifest.json`, and `evidence_index.jsonl` were written. The manifest's `results_jsonl_sha256` matched `sha256sum` of the results file. `human_review_status` was `SEEDED_PARTIAL`, and `maturity_labels` marked the judge `simulated` and the reviews `curated_seed` |
| 4. Tests | First run: 97 collected, 96 passed, 1 skipped (the optional torch test), exit 0. Rerun with fixes: 120 collected, 119 passed, 1 skipped, exit 0 |

## Checking the evidence

The candidate results contain 31 failing cases. The dataset contains 32 planted failures. Comparing the two:

- 31 planted errors were detected.
- 1 was missed (`PY-015`, a known dataset defect).
- There were 0 false alarms on 122 clean cases.

The same author wrote both the planted labels and the graders, so this shows the graders behave as their author intended. It is not independent validation.

The manifest records a `manifest_sha256`, but that value is not the hash of the final file. It is the hash of the manifest serialized without that field. To verify it:

```python
import json, hashlib, glob
path = glob.glob("/tmp/cs/ev-candidate/*.manifest.json")[0]
d = json.load(open(path)); rec = d["artifact_hashes"].pop("manifest_sha256")
assert hashlib.sha256((json.dumps(d, indent=2, sort_keys=True) + "\n").encode()).hexdigest() == rec
```

This held in both recorded runs. The results file hash (`c14ad1c2…856a`) was identical across two separate runs, and identical again in the rerun with fixes, so the offline pipeline is deterministic apart from the run ID and timestamps. Anyone who can write the directory can regenerate every hash, so the check detects accidental change, not deliberate tampering.

## What this case study does *not* show

- **The F1 values do not use independent labels.** In the first run, the values were tautological: the candidate reported `precision = recall = f1 = 1.0` even though 31 cases failed, because `finance_eval/metrics.py` compared each result's `passed` value with itself. With the fix, the metrics compare each result with the case's expected outcome from the dataset's `planted_failure` field, where a pass counts as positive. That label does not come from the grader, but the same author wrote it, so the values are the planted-error cross-check written as precision and recall, not independent validation. The run records the label source in `reference_label_source`. Live and mock runs have no such labels and report `null`.
- **The dataset hash check is only a consistency check.** In the first run, a scratch copy with one edited question and an unchanged `MANIFEST.json` still completed (`FAIL`, 154 cases) and recorded the new hash `de28861664a9…daf03` without any warning. With the fix, the same edit makes `run` and `report` exit with code 2 (`dataset integrity check failed: dataset SHA-256 does not match MANIFEST.json`) before any grading, and no evidence or baseline is written. Someone who rewrites both the data and the manifest would still pass the check.
- **The human review is not real.** The 0.95 judge–human agreement comes from seeded reviews.
- **The baseline is an oracle.** A pass against it does not mean a real model is accurate.
- **No live model was evaluated.** The `mock` provider returns gold answers.

## Production-readiness gaps

See [`docs/evidence-matrix.md`](../evidence-matrix.md#production-readiness-gaps).

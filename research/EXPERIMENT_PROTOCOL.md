# Experiment protocol

## Order of work (as executed)

1. **Benchmark frozen first** (commit `4e766d3`), before any evaluator code for this study existed. This covers the taxonomy, corpus, the 80 cases, and the manifest hashes.
2. Metrics, judge, systems, and runner implemented. The judge prompt (`judge-v1`), decision rule, routing thresholds, and retrieval settings were written from the task definition, not fitted to data.
3. Pipeline debugging was done on the **dev split only**, with the offline stand-in judge, in a temporary directory that is not committed. One change came out of it: the macro-F1 convention when a class is never predicted (see deviations log). It is a metric-definition fix, not a system change.
4. Smoke experiment on **test** with the offline stand-in judge (`config/smoke.yaml`), committed as raw results.
5. LLM experiment on **test** (`config/default.yaml`): **NOT YET RUN.** It needs a user-provided API key and explicit approval of spend; the cap is $2.00 estimated.
6. Holdout confirmation run: **NOT YET RUN.** It may only happen after step 5 is analysed and written up.

## Running

```bash
pip install -r requirements.txt
python -m research.dataset check                                   # verify frozen benchmark hashes
python -m research.run --config research/config/smoke.yaml         # offline, seconds, no API
OPENAI_API_KEY=... python -m research.run --config research/config/default.yaml   # LLM judge
python -m research.run --verify research/results/<experiment_id>   # check artifacts are unmodified
python -m research.paper_tables --experiment research/results/<experiment_id>     # refresh manuscript tables
```

Debug options: `--splits dev` restricts a run to dev. `--allow-holdout` is required for the holdout split, and the manifest records `holdout_used`.

## Rules

- **Never tune on holdout.** Judge prompt, thresholds, retrieval, and decision rule may be debugged on dev only.
- **No silent baseline changes.** Any change to a system, prompt, threshold, or seed after test results exist requires:
  - a new `experiment.name`;
  - an entry in the deviations log below;
  - keeping the earlier results directory.
- **Results are immutable.** The runner refuses to write into an existing directory, and `manifest.json` stores the sha256 of every artifact. Failed and abstained cases stay in `predictions.jsonl` and `errors.jsonl`; nothing is filtered out.
- **No secrets on disk.** The manifest records only the *name* of the key variable (`api_key_env`). The tests assert that a planted key never appears in any artifact.
- **Cost bounds.** `max_cost_usd`, `max_retries`, and `timeout_s` are enforced by `finance_eval.live.LiveRunBudget`. Exceeding the cap aborts the run with `status: aborted_cost_cap` and skips metrics.
- **Judge caching.** Identical judge prompts (temperature 0) are answered from an in-run cache. A1 reuses B3's prompts and A4 reuses B4's, so ablations do not re-sample the model. The counts are in `manifest.judge.calls_made` / `cache_hits`.

## Per-run artifacts (`research/results/<experiment_id>/`)

| File | Content |
|---|---|
| `manifest.json` | git commit + dirty flag, dataset version/hash, case IDs, judge backend/model/provider-reported version, prompt version + system-prompt hash, temperature, retrieval config, routing policy, seed, bootstrap config, command, runtime environment, artifact hashes |
| `predictions.jsonl` | one row per (system, case): label, category, reasons, routing, judge verdict/confidence, rule failures, evidence IDs, latency, cost |
| `evidence.jsonl` | evidence set per (retrieval system, case), with `via` (retrieval or citation), scores, and whether gold evidence was present |
| `judge_raw.jsonl` | every distinct judge request: full user message, raw output text, parse/call errors, tokens, cost, and which systems/cases used it |
| `disagreements.jsonl` | every case where a system's label differs from gold, with reason tags |
| `errors.jsonl` | parse failures, provider errors, exceptions, budget aborts |
| `metrics.json`, `confidence_intervals.json` | all metrics, paired comparisons, bootstrap CIs |
| `report.md` | generated tables and error analysis |

## Deviations log

| Date | Change | Reason | Affects results? |
|---|---|---|---|
| 2026-09-24 | `_f1` returns 0 (not null) when precision or recall is a defined 0 | During dev debugging, macro-F1 was null for a system that never predicts `pass`, which hid a total failure on one class | Metric definition only; applied before any test-split run |

# EvalForge v0.3 integration model

EvalForge keeps its core runtime local-first and dependency-light. External frameworks are optional consumers or producers around the core evidence contract; they are not treated as authorities and they do not bypass the built-in release controls.

## Control flow

```text
cases + approved documents
        |
        +--> deterministic requirements
        +--> local retrieval
                 |
                 v
          heuristic / optional LLM grader
                 |
                 v
       claim-to-evidence control report
        allow | review | block
                 |
        metrics + trace + human review
```

Every result now includes a `controls` object:

```json
{
  "action": "review",
  "release_allowed": false,
  "needs_human_review": true,
  "groundedness": 0.5,
  "citation_coverage": 0.5,
  "retrieval_max_score": 0.72,
  "claim_counts": {"supported": 1, "unsupported": 1},
  "invalid_citation_ids": [],
  "findings": []
}
```

The action has a separate meaning from the grader label:

- `allow`: the configured release controls passed.
- `review`: preserve the answer and route it to the existing human-review queue.
- `block`: do not release automatically; contradictory evidence, invented citation IDs, or a major deterministic instruction failure was detected.

## Ragas or DeepEval

Use the normal JSON or JSONL run export:

```bash
curl -L "http://localhost:8000/api/runs/1/export?format=jsonl" -o run.jsonl
```

The export includes fields that map cleanly to common evaluation test-case formats:

| EvalForge | Typical external field |
|---|---|
| `prompt` | question / input |
| `response` | answer / actual output |
| `expected_label` | expected result or metadata |
| `retrieval_context` | contexts / retrieval context |
| `claim_verdicts` | claim-level factuality evidence |
| `groundedness` | faithfulness / groundedness signal |

Run external metrics as additional evidence. Do not overwrite the native deterministic findings or human decisions with one external score.

## Guardrails AI or NeMo Guardrails

The built-in controls layer is the default local runtime gate. A downstream application can use:

```python
if result["controls"]["release_allowed"]:
    publish(result)
else:
    queue_for_review(result)
```

External guardrail frameworks can be placed before EvalForge (input policy) or after it (application-specific output policy). Keep the EvalForge control report in the audit record so the final decision remains explainable.

## Phoenix or Langfuse

EvalForge records vendor-neutral trace events in SQLite:

```bash
curl "http://localhost:8000/api/runs/1/trace"
```

Stages include:

- `run`
- `retrieval`
- `grader`
- `controls`

To mirror the same events to an append-only local JSONL file:

```bash
EVAL_TRACE_JSONL_PATH=data/traces.jsonl uvicorn app.main:app --reload
```

A future adapter can forward this event contract to OpenTelemetry, Phoenix, or Langfuse. The core run does not fail when an observability backend is unavailable.

## Promptfoo and CI regression gates

Promptfoo can continue to generate or red-team candidate outputs. Import those outputs into EvalForge as cases, execute a run, export the report, and gate CI with the included script:

```bash
python scripts/regression_gate.py run.json \
  --min-accuracy 0.80 \
  --max-review-rate 0.25 \
  --max-block-rate 0.05 \
  --min-groundedness 0.75
```

Exit code `0` means the run passed all supplied thresholds. Exit code `1` means at least one regression threshold failed.

## Human review remains authoritative

External metrics, built-in heuristic scores, and LLM graders are evidence—not final truth. `review` and `block` results remain available through the existing review queue and adjudication endpoints:

```text
PENDING -> REVIEWED -> DISAGREEMENT -> ADJUDICATED
```

This preserves EvalForge's original rule: unsupported is not automatically false, and high-risk uncertainty must be resolved by a person.

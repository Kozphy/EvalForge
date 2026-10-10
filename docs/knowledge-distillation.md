# Knowledge distillation evaluation

EvalForge now supports the evaluation and governance stage of **response
distillation**: a teacher produces candidate supervision, a student is trained
outside EvalForge, and paired held-out observations are evaluated here.

This feature does **not** claim to train a model or expose provider logits.
It supplies the reproducible comparison and deployment gate around that
training process.

## Data contract

Use JSONL with one paired observation per line:

| Field | Meaning |
|---|---|
| `case_id`, `prompt` | Stable benchmark identity and input |
| `teacher_response`, `student_response` | Auditable paired outputs |
| `teacher_quality`, `student_quality` | Scores normalized to `[0, 1]` |
| `teacher_cost`, `student_cost` | Same currency or accounting unit |
| `teacher_latency_ms`, `student_latency_ms` | Comparable end-to-end latency |

Quality should come from a frozen EvalForge grader configuration and held-out
golden set. Do not evaluate only on the teacher-generated training examples.

## Run the gate

```bash
python -m research.run_distillation research/example_distillation.jsonl \
  --min-quality-retention 0.90 \
  --max-quality-drop 0.10 \
  --min-cost-reduction 0.50 \
  --min-latency-reduction 0.20 \
  --output distillation-report.json
```

Exit code `0` means every constraint passed. Exit code `2` means at least
one constraint failed, which makes the command suitable for CI.

The report includes aggregate teacher/student quality, quality retention,
absolute quality drop, cost reduction, latency reduction, failed check names,
and a SHA-256 fingerprint of the ordered dataset.

## Recommended production loop

1. Freeze a versioned golden set and grader configuration.
2. Generate teacher responses and review/filter unsafe or incorrect outputs.
3. Train or fine-tune the student outside EvalForge.
4. Run teacher and student on the same held-out prompts.
5. Import paired quality, cost, and latency observations.
6. Require the policy gate before deployment.
7. Preserve the JSON report with the model, dataset, prompt, and Git versions.

## Interpretation

A pass shows that this dataset and policy accepted the observed trade-off. It
does not prove general model equivalence, safety, or production readiness.
Use representative samples, confidence intervals for consequential decisions,
slice-level checks, and human review for high-risk domains.

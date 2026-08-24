# Evidence-Backed LLM Release Pipeline

This pipeline separates **training success** from **release readiness**.

```text
licensed/versioned dataset
        ↓
dataset manifest (SHA-256 + provenance)
        ↓
pretraining / continued pretraining / SFT / DPO
        ↓
checkpoint evaluation
  ├─ perplexity / task metrics
  ├─ EvalForge benchmark
  └─ failure analysis
        ↓
quantization candidate
        ↓
quality regression gate
        ↓
vLLM serving benchmark
  ├─ TTFT
  ├─ p50/p95 latency
  ├─ tokens/sec
  └─ concurrency / VRAM
        ↓
serving regression gate
        ↓
model registry
        ↓
model card
        ↓
candidate → approved
```

## Release evidence

A checkpoint should not be promoted on training loss alone. Store at minimum:

- base model and exact checkpoint
- Git SHA and training config
- dataset manifest and license/provenance note
- validation perplexity and task-specific evaluation
- quantization method and quality delta
- serving hardware/configuration
- TTFT, p50/p95 latency, tokens/sec, concurrency, and VRAM
- known failure cases / limitations

## Suggested stages

- `experiment`: training completed but not release-evaluated
- `candidate`: passes configured quality and serving gates
- `approved`: human-reviewed evidence package accepted for intended use
- `retired`: superseded or unsafe/outdated checkpoint

## Non-goals

Passing these automated gates is not proof of factual correctness, safety, regulatory fitness, or production suitability. High-risk deployments still require domain evaluation and human approval.

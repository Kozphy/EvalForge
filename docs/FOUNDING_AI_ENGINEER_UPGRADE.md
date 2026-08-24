# Founding AI Engineer Upgrade

This branch extends EvalForge toward an industrial multimodal AI platform while preserving its existing local-first evaluation and human-review core.

## Implemented on this branch

- Typed industrial entities for equipment, instruments, tags, connections, and symbols.
- Deterministic overlapping tiling for high-resolution P&ID / engineering drawings.
- Model-agnostic multimodal `VisionAdapter` interface.
- Explicit `UnavailableVisionAdapter` that reports `NOT_RUN` rather than fabricating model execution.
- ISA-5.1-inspired structural validation hooks. This is **not** a formal ISA-5.1 compliance engine.
- Pluggable self-hosted inference backends:
  - Ollama native API.
  - OpenAI-compatible adapter suitable for vLLM/TGI deployments.
- Continuous-evaluation quality gates for accuracy, p95 latency regression, and critical failure rate.
- GitHub Actions CI covering Python 3.11/3.12, pytest, Docker build, and deterministic evaluation tests.

## Target lifecycle

```text
Industrial document
  -> vector/text extraction
  -> tiled vision extraction
  -> domain validation
  -> RAG / model inference
  -> evaluation
  -> quality gate
  -> human review / approval
  -> deployment eligibility
  -> monitoring
  -> audit evidence
```

## GPU / model status

The repository does **not** claim H100/A100, Vertex AI, Qwen-VL, LLaVA, or Florence-2 execution unless a reproducible run is added later. Interfaces are intentionally separated from hardware-dependent execution.

Status convention:

- `VALIDATED`: executed in CI or a documented reproducible environment.
- `EXPERIMENTAL`: implemented but not yet production hardened.
- `REFERENCE`: architecture or integration path only.
- `NOT_RUN`: unavailable credentials, model weights, API, or GPU hardware prevented execution.

## Reference GCP serving architecture

```text
GCS dataset/model artifacts
        |
        v
Artifact Registry -> container image
        |
        v
Vertex AI / GPU endpoint (A100/H100)
        |
        v
vLLM or TGI OpenAI-compatible API
        |
        v
EvalForge inference adapter
        |
        v
Evaluation -> quality gate -> human approval
```

**REFERENCE DEPLOYMENT — NOT VALIDATED ON H100/A100.**

## Next highest-value increments

1. Add a legally distributable synthetic P&ID benchmark fixture and end-to-end extraction evaluator.
2. Add Qwen-VL / LLaVA / Florence-2 optional adapters behind extras.
3. Add PEFT/QLoRA manifests with dataset hash, seed, git SHA, and checkpoint metadata.
4. Add Prometheus request/retrieval/generation latency metrics.
5. Add Terraform for a reference Vertex AI GPU deployment.
6. Run a real GPU benchmark and commit only reproducible measurements and hardware metadata.

## Quality-gate defaults

The current defaults are project-defined demonstration thresholds, not externally validated SLAs:

- maximum accuracy regression: 2 percentage points
- maximum p95 latency regression: 15%
- maximum critical failure rate: 1%

Training success must never automatically imply production deployment. Model promotion should require evaluation, quality-gate success, and explicit approval.

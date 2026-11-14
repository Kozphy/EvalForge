# LLM Training Stack

This module extends EvalForge from evaluation-only workflows into an end-to-end LLM engineering lab.

## Pipeline

```text
TinyGPT pretraining
  -> financial continued pretraining
  -> LoRA / QLoRA SFT
  -> DPO
  -> EvalForge evaluation
  -> quantized vLLM serving
  -> latency benchmark
  -> financial RAG agent
  -> CI / MLOps gates
```

## 1. TinyGPT from scratch

The educational model in `llm_lab/model.py` implements causal self-attention, transformer blocks, tied token/output embeddings, autoregressive loss, and sampling.

```bash
python -m llm_lab.train \
  --data data/general_corpus.txt \
  --output artifacts/tinygpt-base.pt \
  --block-size 256 \
  --layers 6 --heads 6 --embd 384
```

Run the same trainer against a licensed financial corpus for continued pretraining:

```bash
python -m llm_lab.train \
  --data data/financial_corpus/ \
  --output artifacts/tinygpt-finance.pt \
  --lr 1e-4
```

For portfolio and research integrity, record dataset provenance, licenses, date ranges, deduplication rules, contamination checks, token counts, and train/validation splits. Do not commit proprietary filings or licensed datasets unless redistribution is permitted.

## 2. LoRA / QLoRA SFT

Install the LLM dependencies on a CUDA-capable environment:

```bash
pip install -r requirements-llm.txt
```

Expected SFT JSONL schema:

```json
{"text":"<|user|>Explain FCFF.<|assistant|>FCFF is cash flow available to all capital providers..."}
```

Example:

```bash
python -m llm_lab.finetune sft \
  --model Qwen/Qwen2.5-1.5B \
  --data data/financial_sft.jsonl \
  --output artifacts/finance-sft-lora \
  --load-4bit
```

## 3. DPO

Expected preference data should contain the conventional prompt/chosen/rejected fields.

```bash
python -m llm_lab.finetune dpo \
  --model artifacts/finance-sft-lora \
  --data data/financial_preferences.jsonl \
  --output artifacts/finance-dpo-lora \
  --load-4bit
```

DPO data should encode concrete preferences such as citation quality, unsupported-claim avoidance, calculation correctness, calibrated uncertainty, and compliance with financial-analysis instructions rather than vague style preferences.

## 4. Evaluation

Use EvalForge as the regression and adjudication layer. A useful release gate compares base, continued-pretrained, SFT, and DPO checkpoints on the same frozen benchmark.

Track at minimum:

- task accuracy / exact match where applicable
- factual-support and citation metrics
- hallucination / unsupported-claim rate
- refusal and instruction-following errors
- calibration by confidence bucket
- latency, throughput, token usage, and GPU memory
- slice metrics by task, source type, time period, and difficulty

Never promote a checkpoint based only on training loss.

## 5. Quantization and vLLM serving

`llm_lab/serve.py` exposes a simple FastAPI endpoint backed by vLLM. Run vLLM on a supported Linux/CUDA host.

```bash
python -m llm_lab.serve \
  --model artifacts/finance-dpo-merged \
  --port 9000
```

Use a supported quantized checkpoint or vLLM quantization option when benchmarking FP16/BF16 against AWQ/GPTQ or other supported formats. Record accuracy deltas alongside latency gains.

## 6. Latency benchmark

```bash
python -m llm_lab.benchmark \
  --url http://127.0.0.1:9000/generate \
  --requests 50 \
  --max-tokens 128
```

The smoke benchmark reports mean, p50, p95, requests/sec, and output characters/sec. A production benchmark should additionally measure tokens/sec, time-to-first-token, concurrent load, queue time, GPU utilization, memory, cold start, prompt lengths, and output-length buckets.

## 7. RAG / agent

`llm_lab/rag_agent.py` provides a deliberately small retrieval-and-generation loop. It retrieves evidence, constructs a citation-constrained prompt, and delegates generation to any callable model client.

The next production step is to replace simple TF-IDF with versioned embedding retrieval plus reranking while retaining EvalForge's evidence IDs and human-review workflow.

## 8. CI / MLOps

`.github/workflows/llm-lab-ci.yml` runs CPU smoke tests without requiring an expensive GPU runner.

Recommended GPU release pipeline:

```text
code + dataset manifest
 -> unit tests
 -> data validation / contamination checks
 -> tiny training smoke run
 -> full training job
 -> checkpoint + tokenizer + config artifact
 -> frozen EvalForge benchmark
 -> quality / safety / latency gates
 -> quantization
 -> serving canary
 -> benchmark + regression comparison
 -> model registry promotion
 -> rollback metadata
```

Every experiment should capture Git SHA, dataset version, model ID, tokenizer ID, seed, hyperparameters, hardware, wall time, package lock, metrics, and artifact hashes.

## Roadmap

1. Add streaming dataset ingestion and dataset manifests.
2. Add validation split, perplexity evaluation, warmup/cosine LR schedule, gradient accumulation, resume/checkpoint support, and distributed training.
3. Add explicit continued-pretraining support for Hugging Face foundation models.
4. Add SFT/DPO data validators and chat-template handling.
5. Add lm-eval style task adapters plus EvalForge regression export.
6. Add AWQ/GPTQ quantization jobs and accuracy-before/after reports.
7. Add async/concurrent vLLM benchmarks with TTFT and tokens/sec.
8. Add embedding retriever, reranker, tool registry, agent traces, guardrails, and human approval.
9. Add MLflow/W&B-compatible experiment logging and model registry metadata.
10. Add GPU CI/release workflows triggered manually or by protected tags.

## Scope

This branch is an engineering scaffold, not a claim that a production financial foundation model has already been trained. GPU training, large-corpus ingestion, and benchmark results require an actual compute environment and appropriately licensed datasets.

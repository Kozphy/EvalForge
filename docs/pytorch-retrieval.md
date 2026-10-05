# Optional PyTorch retrieval backend

EvalForge keeps TF-IDF as the zero-download default and now offers an optional
PyTorch backend for local tensor-based retrieval experiments.

## Install

```bash
pip install -r requirements-torch.txt
```

For a CUDA-specific PyTorch build, use the official PyTorch installation
selector and then install the base requirements separately.

## Enable

```bash
# PowerShell
$env:EVAL_RETRIEVAL_BACKEND = "torch"
$env:EVAL_TORCH_DEVICE = "auto"

# macOS / Linux
export EVAL_RETRIEVAL_BACKEND=torch
export EVAL_TORCH_DEVICE=auto
```

Supported settings:

| Variable | Default | Purpose |
|---|---:|---|
| `EVAL_RETRIEVAL_BACKEND` | `tfidf` | `tfidf` or `torch` |
| `EVAL_TORCH_DEVICE` | `auto` | `auto`, `cpu`, `cuda`, or another PyTorch device |
| `EVAL_TORCH_RETRIEVAL_DIMENSIONS` | `2048` | Signed hashing vector width |
| `EVAL_TORCH_RETRIEVAL_BATCH_SIZE` | `128` | Number of chunks encoded per tensor batch |

## Design

The backend uses deterministic signed feature hashing rather than downloading a
pretrained model. PyTorch handles tensor construction, normalization, optional
GPU placement, batched cosine similarity, and ranking.

This makes the feature:

- local-first and reproducible;
- usable without model weights or API keys;
- suitable for testing CPU/GPU execution paths;
- intentionally lexical rather than semantic.

For semantic retrieval, the next compatible extension is a
`sentence-transformers` adapter with explicit model revision pinning, local
model caching, and benchmark comparisons against both TF-IDF and hashed-tensor
retrieval.

## Run tests

```bash
pytest -q
```

The PyTorch-specific test module skips automatically when `torch` is not
installed, so the base dependency path remains lightweight.

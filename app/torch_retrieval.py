from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable


_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


@dataclass(frozen=True)
class TorchRetrievalConfig:
    """Configuration for the lightweight local PyTorch retrieval backend.

    This backend intentionally avoids model downloads. It projects tokens into a
    deterministic signed hashing space and uses PyTorch for batched tensor
    construction, normalization, device placement, and cosine ranking.
    """

    dimensions: int = 2048
    batch_size: int = 128
    device: str = "auto"

    def resolved_device(self, torch_module: object) -> str:
        if self.device != "auto":
            return self.device
        return "cuda" if torch_module.cuda.is_available() else "cpu"


def _import_torch():
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - exercised without optional dependency
        raise RuntimeError(
            "PyTorch retrieval was requested but torch is not installed. "
            "Install it with: pip install -r requirements-torch.txt"
        ) from exc
    return torch


def _token_projection(token: str, dimensions: int) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
    index = int.from_bytes(digest[:8], "big") % dimensions
    sign = 1.0 if digest[8] & 1 else -1.0
    return index, sign


def _encode_batch(texts: Iterable[str], dimensions: int, device: str):
    torch = _import_torch()
    texts = list(texts)
    matrix = torch.zeros((len(texts), dimensions), dtype=torch.float32, device=device)

    for row, text in enumerate(texts):
        for token in _TOKEN_RE.findall(text.casefold()):
            index, sign = _token_projection(token, dimensions)
            matrix[row, index] += sign

    return torch.nn.functional.normalize(matrix, p=2, dim=1, eps=1e-12)


def rank_texts(
    query: str,
    texts: list[str],
    *,
    top_k: int,
    config: TorchRetrievalConfig | None = None,
) -> list[tuple[int, float]]:
    """Return ``(text_index, cosine_score)`` pairs ordered by relevance."""

    if not texts or top_k <= 0:
        return []

    torch = _import_torch()
    cfg = config or TorchRetrievalConfig()
    if cfg.dimensions < 64:
        raise ValueError("dimensions must be at least 64")
    if cfg.batch_size < 1:
        raise ValueError("batch_size must be positive")

    device = cfg.resolved_device(torch)
    query_vector = _encode_batch([query], cfg.dimensions, device)
    scored: list[tuple[int, float]] = []

    with torch.inference_mode():
        for start in range(0, len(texts), cfg.batch_size):
            batch = texts[start : start + cfg.batch_size]
            batch_vectors = _encode_batch(batch, cfg.dimensions, device)
            similarities = (batch_vectors @ query_vector.T).squeeze(1).detach().cpu()
            scored.extend(
                (start + offset, float(score))
                for offset, score in enumerate(similarities.tolist())
            )

    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored[: min(top_k, len(scored))]

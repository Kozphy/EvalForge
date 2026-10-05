"""Lightweight local PyTorch retrieval backend for EvalForge.

This module provides a deterministic, weight-free retrieval backend that uses
PyTorch tensors for batched encoding and cosine ranking.  It intentionally
avoids downloading model weights: tokens are projected into a fixed-dimension
signed hashing space using BLAKE2b, making results fully reproducible across
runs and machines.

Typical usage::

    from app.torch_retrieval import TorchRetrievalConfig, rank_texts

    results = rank_texts(
        "Is land depreciated?",
        ["Land is not depreciated.", "Mars is a planet."],
        top_k=1,
        config=TorchRetrievalConfig(dimensions=512, device="cpu"),
    )
    # results == [(0, <cosine_score>)]
"""

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

    Attributes:
        dimensions: Size of the hashing embedding space.  Higher values reduce
            collision probability at the cost of memory.  Must be at least 64.
            Defaults to 2048.
        batch_size: Number of corpus texts encoded in each PyTorch forward pass.
            Tune to fit GPU/CPU memory.  Defaults to 128.
        device: PyTorch device string (``"cpu"``, ``"cuda"``, ``"cuda:0"``, …)
            or ``"auto"`` to select CUDA when available and fall back to CPU.
            Defaults to ``"auto"``.
    """

    dimensions: int = 2048
    batch_size: int = 128
    device: str = "auto"

    def resolved_device(self, torch_module: object) -> str:
        """Resolve ``"auto"`` to the best available PyTorch device.

        Args:
            torch_module: The imported ``torch`` module, passed in to avoid a
                second import inside the dataclass.

        Returns:
            ``"cuda"`` when a CUDA device is available and ``self.device`` is
            ``"auto"``; otherwise ``self.device`` unchanged.
        """
        if self.device != "auto":
            return self.device
        return "cuda" if torch_module.cuda.is_available() else "cpu"


def _import_torch():
    """Lazily import PyTorch, raising a clear error when it is absent.

    Returns:
        The imported ``torch`` module.

    Raises:
        RuntimeError: If ``torch`` is not installed, with a pointer to
            ``requirements-torch.txt``.
    """
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - exercised without optional dependency
        raise RuntimeError(
            "PyTorch retrieval was requested but torch is not installed. "
            "Install it with: pip install -r requirements-torch.txt"
        ) from exc
    return torch


def _token_projection(token: str, dimensions: int) -> tuple[int, float]:
    """Map a single token to a ``(index, sign)`` pair via BLAKE2b hashing.

    The projection is deterministic and stateless: the same token always maps
    to the same index and sign regardless of call order or environment.

    Args:
        token: A single lower-cased word token.
        dimensions: Size of the target embedding dimension.

    Returns:
        A ``(index, sign)`` tuple where *index* is in ``[0, dimensions)`` and
        *sign* is ``+1.0`` or ``-1.0``.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
    index = int.from_bytes(digest[:8], "big") % dimensions
    sign = 1.0 if digest[8] & 1 else -1.0
    return index, sign


def _encode_batch(texts: Iterable[str], dimensions: int, device: str):
    """Encode a batch of texts into L2-normalised hashing vectors.

    Each text is tokenised with :data:`_TOKEN_RE`, each token is projected via
    :func:`_token_projection`, and the resulting signed counts are accumulated
    into a float32 tensor row.  The full matrix is then L2-normalised so that
    dot products equal cosine similarities.

    Args:
        texts: Iterable of raw text strings to encode.
        dimensions: Embedding dimension; must match the value used for the query.
        device: PyTorch device string (e.g. ``"cpu"`` or ``"cuda"``).

    Returns:
        A ``torch.Tensor`` of shape ``(len(texts), dimensions)`` with dtype
        ``float32`` on *device*, where each row is L2-normalised.
    """
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
    """Rank texts against a query using batched PyTorch cosine similarity.

    The query and each batch of corpus texts are encoded with
    :func:`_encode_batch` and scored via matrix–vector multiplication.
    Results are sorted by descending score; ties are broken by original index.

    Args:
        query: Free-text search query.
        texts: Ordered list of corpus strings to rank.
        top_k: Maximum number of results to return.  Must be positive.
        config: Backend configuration.  Uses :class:`TorchRetrievalConfig`
            defaults when ``None``.

    Returns:
        A list of up to *top_k* ``(text_index, cosine_score)`` pairs ordered
        by descending relevance.  Returns an empty list when *texts* is empty
        or *top_k* is zero.

    Raises:
        ValueError: If ``config.dimensions < 64`` or ``config.batch_size < 1``.
        RuntimeError: If ``torch`` is not installed.
    """
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

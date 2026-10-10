"""Retrieval module for EvalForge.

Chunks reference documents and ranks them against a query using a
selectable backend.  The default backend is TF-IDF (scikit-learn).
An optional PyTorch deterministic hashing backend is available when
``torch`` is installed.

Backend selection (in priority order):

1. The ``backend`` keyword argument passed directly to :func:`retrieve`.
2. The ``EVAL_RETRIEVAL_BACKEND`` environment variable (``tfidf`` or ``torch``).
3. Falls back to ``tfidf``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """An immutable slice of a reference document used for retrieval.

    Attributes:
        document_id: Database ID of the parent document.
        title: Human-readable title of the parent document.
        chunk_id: Stable string identifier in the form ``doc-{id}-chunk-{n}``.
        text: Cleaned text content of this chunk.
    """

    document_id: int
    title: str
    chunk_id: str
    text: str


def chunk_text(document_id: int, title: str, content: str, max_chars: int = 900) -> list[Chunk]:
    """Split a document into overlapping-free, size-bounded text chunks.

    The algorithm splits on blank lines first (paragraph boundaries), then
    falls back to sentence boundaries when a single paragraph exceeds
    ``max_chars``.  Consecutive paragraphs are merged into the same chunk
    until adding the next one would exceed the limit.

    Args:
        document_id: Database ID of the source document.
        title: Human-readable title used in every returned :class:`Chunk`.
        content: Raw document text to be chunked.
        max_chars: Soft upper bound (in characters) for each chunk.  Defaults
            to 900.

    Returns:
        An ordered list of :class:`Chunk` objects.  Empty when *content*
        contains no non-whitespace text.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    chunks: list[Chunk] = []
    buffer = ""
    index = 0

    def flush(value: str) -> None:
        nonlocal index
        cleaned = value.strip()
        if cleaned:
            chunks.append(
                Chunk(
                    document_id=document_id,
                    title=title,
                    chunk_id=f"doc-{document_id}-chunk-{index}",
                    text=cleaned,
                )
            )
            index += 1

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            sentences = re.split(r"(?<=[.!?。！？])\s+", paragraph)
            for sentence in sentences:
                if buffer and len(buffer) + len(sentence) + 1 > max_chars:
                    flush(buffer)
                    buffer = ""
                buffer = f"{buffer} {sentence}".strip()
            continue

        if buffer and len(buffer) + len(paragraph) + 2 > max_chars:
            flush(buffer)
            buffer = ""
        buffer = f"{buffer}\n\n{paragraph}".strip()

    flush(buffer)
    return chunks


def _import_sklearn():
    """Lazily import scikit-learn to defer scipy DLL loading until first use.

    sklearn depends on scipy, whose compiled extensions (e.g. ``_qmc_cy``) are
    loaded the moment ``sklearn`` is first imported.  On Windows machines with
    Application Control policies those DLLs may be blocked, which would prevent
    the entire application from starting if the import were at module level.
    Deferring to call-time means the app starts successfully and only the tfidf
    code path raises an error.

    Returns:
        A ``(TfidfVectorizer, cosine_similarity)`` tuple ready for use.

    Raises:
        RuntimeError: If scikit-learn or its scipy dependency cannot be loaded,
            with a hint to switch to the PyTorch backend.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: PLC0415
        from sklearn.metrics.pairwise import cosine_similarity  # noqa: PLC0415
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "TF-IDF retrieval requires scikit-learn/scipy but they could not be "
            "loaded: " + str(exc) + ". "
            "Set EVAL_RETRIEVAL_BACKEND=torch (and install requirements-torch.txt) "
            "to use the PyTorch backend instead."
        ) from exc
    return TfidfVectorizer, cosine_similarity


def _tfidf_rank(query: str, corpus: list[str], top_k: int) -> list[tuple[int, float]]:
    """Rank corpus texts against a query using TF-IDF cosine similarity.

    Args:
        query: The search string.
        corpus: Ordered list of document texts to rank.
        top_k: Maximum number of results to return.

    Returns:
        Up to *top_k* ``(corpus_index, similarity_score)`` pairs sorted by
        descending similarity.  Scores are raw cosine values in ``[0, 1]``.
    """
    TfidfVectorizer, cosine_similarity = _import_sklearn()
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(corpus + [query])
    similarities = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    ranked = similarities.argsort()[::-1][:top_k]
    return [(int(idx), float(similarities[idx])) for idx in ranked]


def _torch_rank(query: str, corpus: list[str], top_k: int) -> list[tuple[int, float]]:
    """Rank corpus texts against a query using the PyTorch hashing backend.

    Configuration is read from environment variables:

    * ``EVAL_TORCH_RETRIEVAL_DIMENSIONS`` — embedding dimension (default 2048).
    * ``EVAL_TORCH_RETRIEVAL_BATCH_SIZE`` — texts per batch (default 128).
    * ``EVAL_TORCH_DEVICE`` — ``cpu``, ``cuda``, or ``auto`` (default ``auto``).

    Args:
        query: The search string.
        corpus: Ordered list of document texts to rank.
        top_k: Maximum number of results to return.

    Returns:
        Up to *top_k* ``(corpus_index, cosine_score)`` pairs sorted by
        descending score.
    """
    from .torch_retrieval import TorchRetrievalConfig, rank_texts

    config = TorchRetrievalConfig(
        dimensions=int(os.getenv("EVAL_TORCH_RETRIEVAL_DIMENSIONS", "2048")),
        batch_size=int(os.getenv("EVAL_TORCH_RETRIEVAL_BATCH_SIZE", "128")),
        device=os.getenv("EVAL_TORCH_DEVICE", "auto"),
    )
    return rank_texts(query, corpus, top_k=top_k, config=config)


def retrieve(
    query: str,
    documents: list[dict],
    top_k: int = 4,
    *,
    backend: str | None = None,
) -> list[dict]:
    """Retrieve the most relevant document chunks for a query.

    Documents are chunked, ranked by the selected backend, and returned as
    structured dicts suitable for inclusion in grader results.

    The public ``score`` field is clamped to ``[0, 1]``.  The PyTorch signed-
    hashing backend can produce negative cosine similarities; clamping preserves
    the existing contract for callers that display or threshold on this value.

    Args:
        query: Free-text search query.
        documents: List of document dicts, each with ``id`` (int), ``title``
            (str), and ``content`` (str) keys.
        top_k: Maximum number of chunks to return.  Defaults to 4.
        backend: Override the retrieval backend for this call.  Accepted values
            are ``"tfidf"`` and ``"torch"``.  When ``None`` the value of
            ``EVAL_RETRIEVAL_BACKEND`` is used, falling back to ``"tfidf"``.

    Returns:
        A list of up to *top_k* result dicts, each containing:

        * ``document_id`` (int)
        * ``title`` (str)
        * ``chunk_id`` (str)
        * ``text`` (str)
        * ``score`` (float) — clamped cosine similarity in ``[0, 1]``
        * ``retrieval_backend`` (str) — the backend that produced this result

        Returns an empty list when there are no chunks or ``top_k <= 0``.

    Raises:
        ValueError: If *backend* (or ``EVAL_RETRIEVAL_BACKEND``) is not one of
            the recognised values.
        RuntimeError: If the ``tfidf`` backend is requested but scikit-learn /
            scipy cannot be loaded.
    """
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_text(document["id"], document["title"], document["content"]))
    if not chunks or top_k <= 0:
        return []

    corpus = [chunk.text for chunk in chunks]
    selected_backend = (backend or os.getenv("EVAL_RETRIEVAL_BACKEND", "tfidf")).strip().lower()
    if selected_backend == "tfidf":
        ranked = _tfidf_rank(query, corpus, top_k)
    elif selected_backend == "torch":
        ranked = _torch_rank(query, corpus, top_k)
    else:
        raise ValueError(f"Unsupported retrieval backend: {selected_backend}")

    results: list[dict] = []
    for idx, raw_score in ranked:
        chunk = chunks[idx]
        # Signed hashing can produce negative cosine similarity. Public retrieval
        # scores retain the existing bounded 0..1 contract.
        score = max(0.0, min(1.0, raw_score))
        results.append(
            {
                "document_id": chunk.document_id,
                "title": chunk.title,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "score": score,
                "retrieval_backend": selected_backend,
            }
        )
    return results

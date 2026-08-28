from __future__ import annotations

import os
import re
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class Chunk:
    document_id: int
    title: str
    chunk_id: str
    text: str


def chunk_text(document_id: int, title: str, content: str, max_chars: int = 900) -> list[Chunk]:
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


def _tfidf_rank(query: str, corpus: list[str], top_k: int) -> list[tuple[int, float]]:
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(corpus + [query])
    similarities = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    ranked = similarities.argsort()[::-1][:top_k]
    return [(int(idx), float(similarities[idx])) for idx in ranked]


def _torch_rank(query: str, corpus: list[str], top_k: int) -> list[tuple[int, float]]:
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

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class Chunk:
    document_id: int
    title: str
    chunk_id: str
    text: str


def chunk_text(document_id: int, title: str, content: str, max_chars: int = 900) -> list[Chunk]:
    """Split a document into stable, citation-friendly chunks.

    Long paragraphs are split on sentence boundaries. Empty content is ignored and
    chunk IDs remain deterministic for the same document and content ordering.
    """
    if max_chars < 20:
        raise ValueError("max_chars must be at least 20")

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


def _cosine_scores(vectorizer: TfidfVectorizer, corpus: list[str], query: str) -> np.ndarray:
    matrix = vectorizer.fit_transform(corpus + [query])
    return cosine_similarity(matrix[-1], matrix[:-1]).flatten()


def retrieve(
    query: str,
    documents: list[dict[str, Any]],
    top_k: int = 4,
    *,
    min_score: float = 0.0,
    word_weight: float = 0.7,
) -> list[dict[str, Any]]:
    """Retrieve evidence chunks with hybrid word and character TF-IDF ranking.

    Word n-grams capture semantic keywords while character n-grams improve recall
    for identifiers, spelling variants, acronyms, and multilingual text. The
    function remains local and deterministic, and returns citation-ready metadata.
    """
    clean_query = query.strip()
    if not clean_query or top_k <= 0:
        return []
    if not 0.0 <= min_score <= 1.0:
        raise ValueError("min_score must be between 0 and 1")
    if not 0.0 <= word_weight <= 1.0:
        raise ValueError("word_weight must be between 0 and 1")

    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(
            chunk_text(
                int(document["id"]),
                str(document["title"]),
                str(document["content"]),
            )
        )
    if not chunks:
        return []

    corpus = [chunk.text for chunk in chunks]
    word_scores = _cosine_scores(
        TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1),
        corpus,
        clean_query,
    )
    char_scores = _cosine_scores(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1),
        corpus,
        clean_query,
    )
    scores = (word_weight * word_scores) + ((1.0 - word_weight) * char_scores)
    ranked = np.argsort(-scores, kind="stable")[:top_k]

    results: list[dict[str, Any]] = []
    for rank, idx in enumerate(ranked, start=1):
        score = float(scores[int(idx)])
        if score < min_score:
            continue
        chunk = chunks[int(idx)]
        results.append(
            {
                "document_id": chunk.document_id,
                "title": chunk.title,
                "chunk_id": chunk.chunk_id,
                "citation": f"[{chunk.title} · {chunk.chunk_id}]",
                "text": chunk.text,
                "score": max(0.0, min(1.0, score)),
                "rank": rank,
                "retrieval_method": "hybrid_tfidf_word_char",
            }
        )
    return results

from __future__ import annotations

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


def retrieve(query: str, documents: list[dict], top_k: int = 4) -> list[dict]:
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_text(document["id"], document["title"], document["content"]))
    if not chunks:
        return []

    corpus = [chunk.text for chunk in chunks]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(corpus + [query])
    similarities = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    ranked = similarities.argsort()[::-1][:top_k]

    results: list[dict] = []
    for idx in ranked:
        score = float(similarities[idx])
        chunk = chunks[int(idx)]
        results.append(
            {
                "document_id": chunk.document_id,
                "title": chunk.title,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "score": max(0.0, min(1.0, score)),
            }
        )
    return results

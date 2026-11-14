from dataclasses import dataclass
from typing import Callable, Iterable
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class Document:
    id: str
    text: str


class LocalRetriever:
    def __init__(self, docs: Iterable[Document]):
        self.docs = list(docs)
        if not self.docs:
            raise ValueError("at least one document is required")
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform([d.text for d in self.docs])

    def search(self, query: str, k: int = 4):
        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix)[0]
        order = scores.argsort()[::-1][:k]
        return [(self.docs[i], float(scores[i])) for i in order]


class FinancialRAGAgent:
    """Minimal tool-using RAG loop; generator(prompt) can be vLLM, HF, or an API client."""

    def __init__(self, retriever: LocalRetriever, generator: Callable[[str], str]):
        self.retriever = retriever
        self.generator = generator

    def answer(self, question: str, k: int = 4) -> dict:
        hits = self.retriever.search(question, k=k)
        context = "\n\n".join(f"[{doc.id}] {doc.text}" for doc, _ in hits)
        prompt = (
            "Answer the financial question using only the supplied evidence. "
            "Cite source IDs in square brackets. If evidence is insufficient, say so.\n\n"
            f"Evidence:\n{context}\n\nQuestion: {question}\nAnswer:"
        )
        answer = self.generator(prompt)
        return {
            "answer": answer,
            "sources": [{"id": d.id, "score": s} for d, s in hits],
            "prompt": prompt,
        }

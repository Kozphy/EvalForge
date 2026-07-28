import pytest

pytest.importorskip("torch")

from app.retrieval import retrieve
from app.torch_retrieval import TorchRetrievalConfig, rank_texts


def test_rank_texts_prefers_lexically_related_content() -> None:
    texts = [
        "Land normally has an unlimited useful life and is not depreciated.",
        "Mars is a planet in the Solar System.",
    ]
    ranked = rank_texts(
        "Is land depreciated?",
        texts,
        top_k=2,
        config=TorchRetrievalConfig(dimensions=512, batch_size=1, device="cpu"),
    )
    assert ranked[0][0] == 0


def test_retrieve_supports_torch_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_TORCH_DEVICE", "cpu")
    monkeypatch.setenv("EVAL_TORCH_RETRIEVAL_DIMENSIONS", "512")
    docs = [
        {
            "id": 1,
            "title": "Accounting",
            "content": "Land normally has an unlimited useful life and is not depreciated.",
        },
        {
            "id": 2,
            "title": "Astronomy",
            "content": "Mars is a planet in the Solar System.",
        },
    ]

    results = retrieve("Is land depreciated?", docs, top_k=2, backend="torch")

    assert results[0]["document_id"] == 1
    assert results[0]["retrieval_backend"] == "torch"
    assert 0.0 <= results[0]["score"] <= 1.0


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported retrieval backend"):
        retrieve(
            "query",
            [{"id": 1, "title": "Doc", "content": "content"}],
            backend="unknown",
        )

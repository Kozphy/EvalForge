import pytest

from app.retrieval import chunk_text, retrieve


def sample_documents() -> list[dict]:
    return [
        {
            "id": 1,
            "title": "Accounting",
            "content": "Land normally has an unlimited useful life and is not depreciated.\n\nEquipment may be depreciated.",
        },
        {
            "id": 2,
            "title": "Astronomy",
            "content": "Mars is a planet in the Solar System.",
        },
    ]


def test_chunk_text_and_retrieve() -> None:
    docs = sample_documents()
    chunks = chunk_text(1, "Accounting", docs[0]["content"], max_chars=80)
    assert chunks

    results = retrieve("Is land depreciated?", docs, top_k=2)

    assert results[0]["document_id"] == 1
    assert "Land" in results[0]["text"]
    assert results[0]["rank"] == 1
    assert results[0]["citation"].startswith("[Accounting · doc-1-chunk-")
    assert results[0]["retrieval_method"] == "hybrid_tfidf_word_char"


def test_character_retrieval_handles_identifier_variation() -> None:
    docs = [
        {
            "id": 10,
            "title": "Controls",
            "content": "Control identifier ACCT-REV-001 requires quarterly revenue reconciliation.",
        },
        {
            "id": 11,
            "title": "Unrelated",
            "content": "The office fire drill occurs each year.",
        },
    ]

    results = retrieve("ACCT REV 001 reconciliation", docs, top_k=1)

    assert results[0]["document_id"] == 10
    assert results[0]["score"] > 0


def test_min_score_filters_weak_evidence() -> None:
    results = retrieve("quantum entanglement", sample_documents(), top_k=2, min_score=0.8)
    assert results == []


def test_empty_query_and_invalid_options() -> None:
    assert retrieve("   ", sample_documents()) == []
    assert retrieve("land", sample_documents(), top_k=0) == []

    with pytest.raises(ValueError, match="min_score"):
        retrieve("land", sample_documents(), min_score=1.1)
    with pytest.raises(ValueError, match="word_weight"):
        retrieve("land", sample_documents(), word_weight=-0.1)
    with pytest.raises(ValueError, match="max_chars"):
        chunk_text(1, "Doc", "content", max_chars=10)

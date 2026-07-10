from app.retrieval import chunk_text, retrieve


def test_chunk_text_and_retrieve() -> None:
    docs = [
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
    chunks = chunk_text(1, "Accounting", docs[0]["content"], max_chars=80)
    assert chunks
    results = retrieve("Is land depreciated?", docs, top_k=2)
    assert results[0]["document_id"] == 1
    assert "Land" in results[0]["text"]

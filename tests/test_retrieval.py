"""Tests for the TF-IDF retrieval backend (``app.retrieval``).

Verifies that:

* ``chunk_text`` splits a multi-paragraph document into at least one chunk.
* ``retrieve`` returns results ranked so the most relevant document appears
  first, with the expected ``document_id`` and text content.

All tests in this module depend on scikit-learn / scipy and are therefore
decorated with ``@requires_sklearn``.  They are skipped automatically on
hosts where those packages cannot be loaded (e.g. Application Control DLL
blocks on Windows).
"""

from __future__ import annotations

import pytest

from app.retrieval import chunk_text, retrieve
from tests.conftest import requires_sklearn


@requires_sklearn
def test_chunk_text_and_retrieve() -> None:
    """TF-IDF retrieval ranks the most relevant document chunk first.

    Creates two documents (accounting and astronomy), splits the accounting
    document into chunks, then retrieves the top-2 chunks for a depreciation
    query.  Asserts that the top result belongs to the accounting document and
    contains the word ``"Land"``.
    """
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

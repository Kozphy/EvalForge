"""Tests for the optional PyTorch retrieval backend (``app.torch_retrieval``).

The entire module is skipped when ``torch`` is not installed
(``pytest.importorskip("torch")`` at the top of the file).

Covers three scenarios:

* ``rank_texts`` returns the lexically-related chunk at index 0 when given a
  domain-relevant query.
* ``retrieve`` correctly routes to the torch backend via the ``backend``
  keyword argument, returning results with the expected structure and score
  range.
* Passing an unknown backend name to ``retrieve`` raises ``ValueError``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("torch")

from app.retrieval import retrieve
from app.torch_retrieval import TorchRetrievalConfig, rank_texts


def test_rank_texts_prefers_lexically_related_content() -> None:
    """``rank_texts`` ranks the topically relevant text above an unrelated one.

    Uses a small 512-dimension config with ``batch_size=1`` to keep the test
    fast on CPU.  Asserts that the accounting sentence (index 0) outranks the
    astronomy sentence (index 1) for a depreciation query.
    """
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
    """``retrieve`` routes to the PyTorch backend when ``backend="torch"`` is passed.

    Sets ``EVAL_TORCH_DEVICE=cpu`` and ``EVAL_TORCH_RETRIEVAL_DIMENSIONS=512``
    via ``monkeypatch`` to ensure a deterministic, CPU-only run.  Asserts:

    * The top result belongs to the accounting document (``document_id == 1``).
    * ``retrieval_backend`` in the result dict is ``"torch"``.
    * The score is within the public ``[0, 1]`` contract.

    Args:
        monkeypatch: pytest fixture used to set environment variables for the
            duration of this test only.
    """
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
    """``retrieve`` raises ``ValueError`` for unrecognised backend names.

    Confirms the error message contains ``"Unsupported retrieval backend"`` so
    callers can identify the cause from the exception text alone.
    """
    with pytest.raises(ValueError, match="Unsupported retrieval backend"):
        retrieve(
            "query",
            [{"id": 1, "title": "Doc", "content": "content"}],
            backend="unknown",
        )

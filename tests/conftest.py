"""Shared pytest fixtures and skip helpers for the EvalForge test suite."""

from __future__ import annotations

import pytest


def _sklearn_loadable() -> bool:
    """Return True if sklearn (and its scipy dependency) can be imported."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401, PLC0415
        from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401, PLC0415

        return True
    except Exception:
        return False


#: pytest.mark that skips a test when sklearn/scipy cannot be loaded
#: (e.g. due to Application Control DLL blocking on Windows).
requires_sklearn = pytest.mark.skipif(
    not _sklearn_loadable(),
    reason="scikit-learn / scipy could not be loaded (DLL or import error); skipping tfidf-dependent tests",
)

"""Shared pytest fixtures and skip helpers for the EvalForge test suite."""

from __future__ import annotations

import pytest


def _sklearn_loadable() -> bool:
    """Probe whether scikit-learn and scipy can be imported on this machine.

    On Windows hosts with Application Control policies, scipy's compiled
    extensions (e.g. ``_qmc_cy``) may be blocked at the DLL level.  This
    function catches both ``ImportError`` and any ``OSError`` / ``Exception``
    that a DLL load failure surfaces as.

    Returns:
        ``True`` if ``TfidfVectorizer`` and ``cosine_similarity`` import
        successfully; ``False`` otherwise.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401, PLC0415
        from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401, PLC0415

        return True
    except Exception:
        return False


#: ``pytest.mark`` decorator that skips a test when sklearn/scipy cannot be
#: loaded (e.g. due to an Application Control DLL block on Windows).
#: Apply to any test that exercises the ``tfidf`` retrieval backend, either
#: directly or via an API endpoint that triggers a grading run.
requires_sklearn = pytest.mark.skipif(
    not _sklearn_loadable(),
    reason="scikit-learn / scipy could not be loaded (DLL or import error); skipping tfidf-dependent tests",
)

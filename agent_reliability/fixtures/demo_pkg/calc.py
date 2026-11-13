"""Intentionally buggy baseline used by the local reliability fixture."""


def is_newer(left: str, right: str) -> bool:
    """Return True if left is a newer semver-like version than right.

    Baseline bug: compares dotted versions as plain strings, so
    ``is_newer("1.10.0", "1.9.0")`` returns False.
    """
    return left > right

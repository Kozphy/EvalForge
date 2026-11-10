"""Correct candidate implementation for the local reliability fixture."""


def _parts(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def is_newer(left: str, right: str) -> bool:
    return _parts(left) > _parts(right)

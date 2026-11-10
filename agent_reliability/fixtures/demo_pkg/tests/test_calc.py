from demo_pkg.calc import is_newer


def test_is_newer_basic() -> None:
    assert is_newer("2.0.0", "1.0.0") is True


def test_is_newer_patch_vs_minor() -> None:
    assert is_newer("1.10.0", "1.9.0") is True

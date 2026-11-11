"""Load bundled fixtures and enforce their manifest hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from annotation_eval.schema import Annotation, LabeledItem

DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST_PATH = DATA_DIR / "MANIFEST.json"


class ManifestMismatchError(RuntimeError):
    """A fixture file does not match its recorded sha256."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(name: str, path: Optional[Path] = None, manifest: Optional[dict] = None) -> Path:
    manifest = manifest if manifest is not None else load_manifest()
    if name not in manifest["datasets"]:
        raise KeyError(f"dataset not in manifest: {name}")
    entry = manifest["datasets"][name]
    path = path or DATA_DIR / entry["file"]
    actual = sha256_file(path)
    if actual != entry["sha256"]:
        raise ManifestMismatchError(f"{name}: sha256 {actual} != manifest {entry['sha256']}")
    return path


def _read_jsonl(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_items(name: str, path: Optional[Path] = None, manifest: Optional[dict] = None) -> List[LabeledItem]:
    return [LabeledItem(**row) for row in _read_jsonl(verify(name, path, manifest))]


def load_annotations(name: str, path: Optional[Path] = None, manifest: Optional[dict] = None) -> List[Annotation]:
    return [Annotation(**row) for row in _read_jsonl(verify(name, path, manifest))]

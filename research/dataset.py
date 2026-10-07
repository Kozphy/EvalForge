"""Frozen benchmark: schema, hashing, freezing, leakage checks, loading.

Usage::

    python -m research.dataset check    # verify frozen files match MANIFEST.json
    python -m research.dataset freeze   # write JSONL + manifest from the authoring source
    python -m research.dataset stats    # print label / category distribution
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas import RequirementSpec
from research.datasets import source_v1 as source
from research.taxonomy import CATEGORIES

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
MANIFEST_PATH = DATASETS_DIR / "MANIFEST.json"
CORPUS_PATH = DATASETS_DIR / "corpus" / "kb.jsonl"
SPLITS: tuple[str, ...] = ("dev", "test", "holdout")
NEAR_DUPLICATE_JACCARD = 0.9

Split = Literal["dev", "test", "holdout"]


class CorpusDocument(BaseModel):
    doc_id: str = Field(pattern=r"^KB-\d{2}$")
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


class BenchmarkCase(BaseModel):
    case_id: str = Field(pattern=r"^EFB-\d{3}$")
    dataset_version: str
    split: Split
    prompt: str = Field(min_length=1)
    candidate_response: str = Field(min_length=1)
    requirements: RequirementSpec = Field(default_factory=RequirementSpec)
    gold_label: Literal["pass", "fail"]
    failure_category: str
    gold_evidence_ids: list[str] = Field(min_length=1)
    label_rationale: str = Field(min_length=1)
    ambiguous: bool = False
    provenance: dict
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("failure_category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(f"unknown failure_category {value!r}")
        return value

    @model_validator(mode="after")
    def _label_category_consistent(self) -> "BenchmarkCase":
        if self.gold_label == "pass" and self.failure_category != "none":
            raise ValueError(f"{self.case_id}: pass cases must have failure_category 'none'")
        if self.gold_label == "fail" and self.failure_category == "none":
            raise ValueError(f"{self.case_id}: fail cases need a failure category")
        if self.failure_category == "ambiguous_case" and not self.ambiguous:
            raise ValueError(f"{self.case_id}: ambiguous_case must set ambiguous=true")
        expected = case_content_hash(self.model_dump(mode="json"))
        if expected != self.content_sha256:
            raise ValueError(f"{self.case_id}: content_sha256 does not match case content")
        return self


_HASHED_FIELDS = (
    "case_id",
    "prompt",
    "candidate_response",
    "requirements",
    "gold_label",
    "failure_category",
    "gold_evidence_ids",
    "ambiguous",
)


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def case_content_hash(case: dict) -> str:
    requirements = case.get("requirements") or {}
    if isinstance(requirements, BaseModel):
        requirements = requirements.model_dump(mode="json")
    normalized_requirements = RequirementSpec.model_validate(requirements).model_dump(
        mode="json", exclude_defaults=True
    )
    payload = {field: case.get(field) for field in _HASHED_FIELDS}
    payload["requirements"] = normalized_requirements
    return sha256_bytes(_canonical(payload).encode("utf-8"))


def _jsonl_bytes(rows: Iterable[dict]) -> bytes:
    return "".join(_canonical(row) + "\n" for row in rows).encode("utf-8")


def split_path(split: str) -> Path:
    return DATASETS_DIR / split / "cases.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------------ leakage


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class LeakageFinding:
    kind: str
    case_a: str
    case_b: str
    detail: str


def find_leakage(cases: list[dict], threshold: float = NEAR_DUPLICATE_JACCARD) -> list[LeakageFinding]:
    """Duplicate IDs anywhere; exact or near-duplicate prompt+response across splits."""
    findings: list[LeakageFinding] = []
    seen_ids: dict[str, str] = {}
    for case in cases:
        if case["case_id"] in seen_ids:
            findings.append(LeakageFinding("duplicate_id", seen_ids[case["case_id"]], case["case_id"], case["case_id"]))
        seen_ids[case["case_id"]] = case["case_id"]

    for i, a in enumerate(cases):
        for b in cases[i + 1 :]:
            if a["split"] == b["split"]:
                continue
            if _normalize(a["prompt"]) == _normalize(b["prompt"]):
                findings.append(LeakageFinding("duplicate_prompt", a["case_id"], b["case_id"], "identical prompt"))
                continue
            sim = _jaccard(
                _tokens(a["prompt"] + " " + a["candidate_response"]),
                _tokens(b["prompt"] + " " + b["candidate_response"]),
            )
            if sim >= threshold:
                findings.append(
                    LeakageFinding("near_duplicate", a["case_id"], b["case_id"], f"jaccard={sim:.2f}")
                )
    return findings


# ------------------------------------------------------------------ freeze


def build_frozen_rows() -> tuple[list[dict], dict[str, list[dict]], dict]:
    corpus = [CorpusDocument.model_validate(doc).model_dump() for doc in source.CORPUS]
    by_split: dict[str, list[dict]] = {split: [] for split in SPLITS}
    for raw in source.CASES:
        row = dict(raw)
        row["requirements"] = RequirementSpec.model_validate(row["requirements"]).model_dump(
            mode="json", exclude_defaults=True
        )
        row["dataset_version"] = source.DATASET_VERSION
        row["provenance"] = dict(source.PROVENANCE)
        row["content_sha256"] = case_content_hash(row)
        BenchmarkCase.model_validate(row)
        by_split[row["split"]].append(row)
    meta = {
        "dataset_name": source.DATASET_NAME,
        "version": source.DATASET_VERSION,
        "created": source.CREATED,
        "provenance": source.PROVENANCE,
    }
    return corpus, by_split, meta


def _manifest_for(corpus_bytes: bytes, split_bytes: dict[str, bytes], by_split: dict[str, list[dict]], meta: dict) -> dict:
    corpus_ids = [json.loads(line)["doc_id"] for line in corpus_bytes.decode("utf-8").splitlines()]
    files = {
        "corpus/kb.jsonl": {"sha256": sha256_bytes(corpus_bytes), "n": len(corpus_ids), "ids": corpus_ids},
    }
    distribution: dict[str, dict] = {}
    for split in SPLITS:
        rows = by_split[split]
        files[f"{split}/cases.jsonl"] = {
            "sha256": sha256_bytes(split_bytes[split]),
            "n": len(rows),
            "ids": [row["case_id"] for row in rows],
        }
        distribution[split] = {
            "labels": dict(sorted(Counter(row["gold_label"] for row in rows).items())),
            "categories": dict(sorted(Counter(row["failure_category"] for row in rows).items())),
            "ambiguous": sum(1 for row in rows if row["ambiguous"]),
        }
    combined = hashlib.sha256()
    for name in sorted(files):
        combined.update(name.encode("utf-8"))
        combined.update(files[name]["sha256"].encode("ascii"))
    return {
        **meta,
        "dataset_sha256": combined.hexdigest(),
        "files": files,
        "distribution": distribution,
        "hashing": "sha256 of exact file bytes (UTF-8, LF); dataset_sha256 = sha256 over sorted (path, file sha256)",
    }


def freeze() -> dict:
    corpus, by_split, meta = build_frozen_rows()
    all_cases = [row for split in SPLITS for row in by_split[split]]
    leaks = find_leakage(all_cases)
    if leaks:
        raise SystemExit("Refusing to freeze; leakage found:\n" + "\n".join(map(str, leaks)))
    corpus_ids = {doc["doc_id"] for doc in corpus}
    for row in all_cases:
        unknown = set(row["gold_evidence_ids"]) - corpus_ids
        if unknown:
            raise SystemExit(f"{row['case_id']}: gold evidence ids not in corpus: {sorted(unknown)}")

    corpus_bytes = _jsonl_bytes(corpus)
    split_bytes = {split: _jsonl_bytes(by_split[split]) for split in SPLITS}
    manifest = _manifest_for(corpus_bytes, split_bytes, by_split, meta)

    if MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if existing.get("version") == manifest["version"] and existing.get("dataset_sha256") != manifest["dataset_sha256"]:
            raise SystemExit(
                f"Dataset version {manifest['version']} is already frozen with different content. "
                "Bump DATASET_VERSION in the authoring source instead of editing a frozen version."
            )

    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_bytes(corpus_bytes)
    for split in SPLITS:
        path = split_path(split)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(split_bytes[split])
    MANIFEST_PATH.write_bytes((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return manifest


# ------------------------------------------------------------------ check / load


class DatasetIntegrityError(RuntimeError):
    pass


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise DatasetIntegrityError(f"Missing dataset manifest at {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def verify_integrity() -> dict:
    """Fail closed if any frozen file differs from the manifest."""
    manifest = load_manifest()
    for rel, meta in manifest["files"].items():
        path = DATASETS_DIR / rel
        if not path.exists():
            raise DatasetIntegrityError(f"Missing frozen file {rel}")
        actual = sha256_bytes(path.read_bytes())
        if actual != meta["sha256"]:
            raise DatasetIntegrityError(f"Hash mismatch for {rel}: manifest {meta['sha256']} != file {actual}")
    return manifest


def load_corpus() -> list[CorpusDocument]:
    return [CorpusDocument.model_validate(row) for row in _read_jsonl(CORPUS_PATH)]


def load_split(split: str, *, allow_holdout: bool = False) -> list[BenchmarkCase]:
    if split not in SPLITS:
        raise ValueError(f"Unknown split {split!r}")
    if split == "holdout" and not allow_holdout:
        raise PermissionError(
            "The holdout split is reserved for the final pre-registered run. "
            "Pass allow_holdout=True (CLI: --allow-holdout) only for that run."
        )
    return [BenchmarkCase.model_validate(row) for row in _read_jsonl(split_path(split))]


def check_source_matches_frozen() -> bool:
    corpus, by_split, _ = build_frozen_rows()
    if _jsonl_bytes(corpus) != CORPUS_PATH.read_bytes():
        return False
    return all(_jsonl_bytes(by_split[s]) == split_path(s).read_bytes() for s in SPLITS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.dataset")
    parser.add_argument("command", choices=["freeze", "check", "stats"])
    args = parser.parse_args(argv)
    if args.command == "freeze":
        manifest = freeze()
        print(f"Frozen {manifest['dataset_name']} v{manifest['version']} sha256={manifest['dataset_sha256']}")
        return 0
    manifest = verify_integrity()
    if args.command == "check":
        if not check_source_matches_frozen():
            print("Frozen files verify against MANIFEST.json, but the authoring source has drifted.")
            return 1
        print(f"OK {manifest['dataset_name']} v{manifest['version']} sha256={manifest['dataset_sha256']}")
        return 0
    print(json.dumps(manifest["distribution"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

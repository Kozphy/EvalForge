import json

import pytest

from research import dataset
from research.taxonomy import CATEGORIES, FAILURE_CATEGORIES, PRIORITY


def _all_rows():
    return [json.loads(line) for split in dataset.SPLITS for line in dataset.split_path(split).read_text(encoding="utf-8").splitlines()]


def test_frozen_files_match_manifest_hashes():
    manifest = dataset.verify_integrity()
    assert manifest["version"] == "1.0.0"
    assert set(manifest["files"]) == {"corpus/kb.jsonl", "dev/cases.jsonl", "test/cases.jsonl", "holdout/cases.jsonl"}


def test_authoring_source_has_not_drifted_from_frozen_files():
    assert dataset.check_source_matches_frozen()


def test_every_case_validates_and_hash_matches_content():
    rows = _all_rows()
    assert len(rows) == 80
    for row in rows:
        case = dataset.BenchmarkCase.model_validate(row)
        assert case.content_sha256 == dataset.case_content_hash(row)


def test_tampered_case_is_rejected():
    row = _all_rows()[0]
    row["gold_label"] = "fail" if row["gold_label"] == "pass" else "pass"
    row["failure_category"] = "other" if row["gold_label"] == "fail" else "none"
    with pytest.raises(ValueError):
        dataset.BenchmarkCase.model_validate(row)


def test_manifest_ids_match_split_files():
    manifest = dataset.load_manifest()
    for split in dataset.SPLITS:
        ids = [json.loads(line)["case_id"] for line in dataset.split_path(split).read_text(encoding="utf-8").splitlines()]
        assert ids == manifest["files"][f"{split}/cases.jsonl"]["ids"]


def test_no_split_leakage_or_duplicate_ids():
    assert dataset.find_leakage(_all_rows()) == []


def test_leakage_detector_flags_cross_split_duplicates():
    rows = _all_rows()
    clone = dict(rows[0], case_id="EFB-999", split="holdout")
    kinds = {finding.kind for finding in dataset.find_leakage([rows[0], clone])}
    assert "duplicate_prompt" in kinds


def test_gold_evidence_ids_exist_in_corpus():
    corpus_ids = {doc.doc_id for doc in dataset.load_corpus()}
    for row in _all_rows():
        assert set(row["gold_evidence_ids"]) <= corpus_ids, row["case_id"]


def test_taxonomy_is_complete_and_ordered():
    assert set(PRIORITY) == set(FAILURE_CATEGORIES)
    assert len(PRIORITY) == len(set(PRIORITY))
    for row in _all_rows():
        assert row["failure_category"] in CATEGORIES


def test_holdout_requires_explicit_opt_in():
    with pytest.raises(PermissionError):
        dataset.load_split("holdout")
    assert len(dataset.load_split("holdout", allow_holdout=True)) == 20


def test_provenance_is_labelled_synthetic():
    for row in _all_rows():
        assert row["provenance"]["production_data"] is False
        assert row["provenance"]["source"] == "synthetic_handwritten"

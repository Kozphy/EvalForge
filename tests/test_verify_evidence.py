"""Tamper and malformed-input coverage for the read-only evidence verifier."""
import hashlib
import json

from finance_eval.evidence import write_evidence_bundle
from finance_eval.verify_evidence import verify_bundle


def _fixture(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_bytes(b'{"case_id": "a"}\n')
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    pin = tmp_path / "dataset-manifest.json"
    pin.write_text(json.dumps({"sha256": digest, "dataset_version": "test-v1"}), encoding="utf-8")
    out_dir = tmp_path / "evidence"
    bundle = write_evidence_bundle(
        out_dir,
        model="offline", model_version="v1", prompt_version="p1",
        dataset_version="test-v1", dataset_hash=digest,
        metrics={"accuracy": 1.0}, case_results=[{"case_id": "a", "passed": True}],
        policy={"decision": "PASS"}, regression=None,
        human_review_status="not_requested",
    )
    manifest_path = out_dir / (bundle["run_id"] + ".manifest.json")
    return manifest_path, dataset, pin, bundle["run_id"]


def test_valid_evidence_passes(tmp_path):
    manifest, dataset, pin, _ = _fixture(tmp_path)
    assert verify_bundle(manifest, dataset, pin) == []


def test_modified_results_fail(tmp_path):
    manifest, dataset, pin, run_id = _fixture(tmp_path)
    results = manifest.parent / (run_id + ".results.jsonl")
    results.write_text(results.read_text() + "tampered\n")
    assert "Results JSONL hash mismatch" in verify_bundle(manifest, dataset, pin)


def test_modified_dataset_fails(tmp_path):
    manifest, dataset, pin, _ = _fixture(tmp_path)
    dataset.write_bytes(dataset.read_bytes() + b"changed")
    assert "Dataset file SHA-256 mismatch" in verify_bundle(manifest, dataset, pin)


def test_modified_manifest_fails(tmp_path):
    manifest, dataset, pin, _ = _fixture(tmp_path)
    data = json.loads(manifest.read_text())
    data["policy_decision"] = "OVERRIDDEN"
    manifest.write_text(json.dumps(data))
    assert "Manifest SHA-256 mismatch" in verify_bundle(manifest, dataset, pin)


def test_invalid_run_id_rejected(tmp_path):
    manifest, dataset, pin, _ = _fixture(tmp_path)
    data = json.loads(manifest.read_text())
    data["run_id"] = "../../bad"
    manifest.write_text(json.dumps(data))
    failures = verify_bundle(manifest, dataset, pin)
    assert "Invalid run_id; refusing to resolve results path" in failures


def test_missing_results_fails(tmp_path):
    manifest, dataset, pin, run_id = _fixture(tmp_path)
    (manifest.parent / (run_id + ".results.jsonl")).unlink()
    assert any("Cannot read results JSONL" in issue for issue in verify_bundle(manifest, dataset, pin))

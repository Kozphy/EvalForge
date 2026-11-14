"""Read-only verification of finance evaluation evidence bundles.

This checks byte integrity and schema linkage, not whether an AI claim is true,
whether the evaluator is unbiased, or whether a deployment is safe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

_RUN_ID = re.compile(r"finrun_[0-9a-f]{12}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_bundle(manifest_path: Path, dataset_path: Path, dataset_manifest_path: Path) -> list[str]:
    """Return a list of verification errors; never rewrite evidence files."""
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"Cannot read required manifest: {exc}"]

    if not isinstance(manifest, dict) or not isinstance(dataset_manifest, dict):
        return ["Manifests must be JSON objects"]
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        return ["Invalid run_id; refusing to resolve results path"]

    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, dict):
        return ["Missing artifact_hashes"]
    results_hash = hashes.get("results_jsonl_sha256")
    self_hash = hashes.get("manifest_sha256")
    if not isinstance(results_hash, str) or not _SHA256.fullmatch(results_hash):
        errors.append("Missing or invalid results JSONL SHA-256")
    if not isinstance(self_hash, str) or not _SHA256.fullmatch(self_hash):
        errors.append("Missing or invalid manifest SHA-256")

    results_path = manifest_path.parent / f"{run_id}.results.jsonl"
    try:
        if isinstance(results_hash, str) and _SHA256.fullmatch(results_hash):
            if _sha(results_path) != results_hash:
                errors.append("Results JSONL hash mismatch")
        else:
            _sha(results_path)  # still require evidence artifact to exist
    except OSError as exc:
        errors.append(f"Cannot read results JSONL: {exc}")

    # Writer hashes the canonical JSON payload before adding manifest_sha256.
    # This matches finance_eval.evidence.write_evidence_bundle, not a digital signature.
    if isinstance(self_hash, str) and _SHA256.fullmatch(self_hash):
        unsigned = json.loads(json.dumps(manifest))
        unsigned["artifact_hashes"].pop("manifest_sha256", None)
        canonical = json.dumps(unsigned, indent=2, sort_keys=True) + "\n"
        computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if computed != self_hash:
            errors.append("Manifest SHA-256 mismatch")

    expected = dataset_manifest.get("sha256")
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        errors.append("Invalid pinned dataset SHA-256")
    else:
        if manifest.get("dataset_sha256") != expected:
            errors.append("Evaluation dataset hash differs from pinned manifest")
        if manifest.get("dataset_version") != dataset_manifest.get("dataset_version"):
            errors.append("Evaluation dataset version differs from pinned manifest")
        try:
            if _sha(dataset_path) != expected:
                errors.append("Dataset file SHA-256 mismatch")
        except OSError as exc:
            errors.append(f"Cannot read dataset: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Evaluation finrun_*.manifest.json")
    parser.add_argument("--dataset", type=Path, default=Path("finance_eval/dataset/finance_accounting_v1.jsonl"))
    parser.add_argument("--dataset-manifest", type=Path, default=Path("finance_eval/dataset/MANIFEST.json"))
    args = parser.parse_args()
    failures = verify_bundle(args.manifest, args.dataset, args.dataset_manifest)
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: evidence file, manifest and pinned dataset hashes match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

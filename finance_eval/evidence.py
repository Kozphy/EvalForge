"""Append-only style evaluation evidence (JSON/JSONL)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_evidence_bundle(
    out_dir: Path,
    *,
    model: str,
    model_version: str,
    prompt_version: str,
    dataset_version: str,
    dataset_hash: str,
    metrics: dict[str, Any],
    case_results: list[dict[str, Any]],
    policy: dict[str, Any],
    regression: dict[str, Any] | None,
    human_review_status: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"finrun_{uuid4().hex[:12]}"
    results_path = out_dir / f"{run_id}.results.jsonl"
    with results_path.open("w", encoding="utf-8") as fh:
        for row in case_results:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    failure_classes: dict[str, int] = {}
    for row in case_results:
        for code in row.get("failure_codes") or []:
            failure_classes[code] = failure_classes.get(code, 0) + 1

    maturity = {
        "deterministic_grading": "implemented",
        "llm_judge": "simulated",
        "human_review_seed": "curated_seed",
        "evidence_store": "file_append",
    }
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": utc_now(),
        "model": model,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "dataset_version": dataset_version,
        "dataset_sha256": dataset_hash,
        "metrics": metrics,
        "failure_classes": failure_classes,
        "policy_decision": policy.get("decision"),
        "policy": policy,
        "regression": regression,
        "human_review_status": human_review_status,
        "artifact_hashes": {
            "results_jsonl_sha256": sha256_file(results_path),
        },
        "maturity_labels": maturity,
    }
    if extra:
        if "maturity_labels" in extra and isinstance(extra["maturity_labels"], dict):
            maturity.update(extra["maturity_labels"])
            extra = {k: v for k, v in extra.items() if k != "maturity_labels"}
        manifest.update(extra)
    manifest_path = out_dir / f"{run_id}.manifest.json"
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(payload, encoding="utf-8")
    manifest["artifact_hashes"]["manifest_sha256"] = sha256_text(payload)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    index_path = out_dir / "evidence_index.jsonl"
    with index_path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "timestamp": manifest["timestamp"],
                    "policy_decision": manifest["policy_decision"],
                    "manifest": str(manifest_path.as_posix()),
                    "results": str(results_path.as_posix()),
                }
            )
            + "\n"
        )
    return manifest

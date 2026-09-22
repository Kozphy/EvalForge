"""Append-only evidence records and audit manifests."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.control_plane import SCHEMA_VERSION
from app.control_plane.contracts import new_id
from app.control_plane.evidence.redaction import redact_structure


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_json(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class EvidenceRecord(BaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("ev"))
    experiment_id: str
    run_id: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    sha256: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION


class AuditManifest(BaseModel):
    experiment_id: str
    dataset_version: str | None = None
    candidate: dict[str, Any] = Field(default_factory=dict)
    baseline: dict[str, Any] | None = None
    evaluators: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    regressions: list[dict[str, Any]] = Field(default_factory=list)
    policy_decision: str | None = None
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    evidence_hashes: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    schema_version: str = SCHEMA_VERSION
    manifest_sha256: str = ""


class InMemoryEvidenceStore:
    """Append-only in-memory store (SQLite-backed repo can wrap this later)."""

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []

    def append(self, experiment_id: str, run_id: str, kind: str, payload: dict[str, Any]) -> EvidenceRecord:
        clean = redact_structure(payload)
        record = EvidenceRecord(
            experiment_id=experiment_id,
            run_id=run_id,
            kind=kind,
            payload=clean,
            sha256=sha256_json(clean),
        )
        self._records.append(record)
        return record

    def list_for_experiment(self, experiment_id: str) -> list[EvidenceRecord]:
        return [r for r in self._records if r.experiment_id == experiment_id]

    def build_manifest(
        self,
        *,
        experiment_id: str,
        dataset_version: str | None,
        candidate: dict[str, Any],
        baseline: dict[str, Any] | None,
        evaluators: list[str],
        metrics: dict[str, Any],
        regressions: list[dict[str, Any]],
        policy_decision: str | None,
        approvals: list[dict[str, Any]] | None = None,
    ) -> AuditManifest:
        hashes = {r.evidence_id: r.sha256 for r in self.list_for_experiment(experiment_id)}
        manifest = AuditManifest(
            experiment_id=experiment_id,
            dataset_version=dataset_version,
            candidate=redact_structure(candidate),
            baseline=redact_structure(baseline) if baseline else None,
            evaluators=evaluators,
            metrics=metrics,
            regressions=regressions,
            policy_decision=policy_decision,
            approvals=approvals or [],
            evidence_hashes=hashes,
        )
        manifest.manifest_sha256 = sha256_json(manifest.model_dump(mode="json"))
        return manifest

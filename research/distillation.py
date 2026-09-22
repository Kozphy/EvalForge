"""Auditable teacher-versus-student evaluation for response distillation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping


@dataclass(frozen=True)
class DistillationRecord:
    """One paired observation. Costs use the same currency/unit."""

    case_id: str
    prompt: str
    teacher_response: str
    student_response: str
    teacher_quality: float
    student_quality: float
    teacher_cost: float
    student_cost: float
    teacher_latency_ms: float
    student_latency_ms: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "DistillationRecord":
        record = cls(
            case_id=str(value["case_id"]),
            prompt=str(value["prompt"]),
            teacher_response=str(value["teacher_response"]),
            student_response=str(value["student_response"]),
            teacher_quality=float(value["teacher_quality"]),
            student_quality=float(value["student_quality"]),
            teacher_cost=float(value["teacher_cost"]),
            student_cost=float(value["student_cost"]),
            teacher_latency_ms=float(value["teacher_latency_ms"]),
            student_latency_ms=float(value["student_latency_ms"]),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if not self.case_id.strip() or not self.prompt.strip():
            raise ValueError("case_id and prompt must not be empty")
        if not self.teacher_response.strip() or not self.student_response.strip():
            raise ValueError("teacher_response and student_response must not be empty")
        if not 0 <= self.teacher_quality <= 1 or not 0 <= self.student_quality <= 1:
            raise ValueError("quality scores must be between 0 and 1")
        for name in ("teacher_cost", "student_cost", "teacher_latency_ms", "student_latency_ms"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True)
class DistillationPolicy:
    min_quality_retention: float = 0.90
    min_cost_reduction: float = 0.50
    min_latency_reduction: float = 0.20
    max_student_quality_drop: float = 0.10

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class DistillationReport:
    sample_count: int
    teacher_quality: float
    student_quality: float
    quality_retention: float
    quality_drop: float
    teacher_cost: float
    student_cost: float
    cost_reduction: float
    teacher_latency_ms: float
    student_latency_ms: float
    latency_reduction: float
    passed: bool
    failed_checks: tuple[str, ...]
    dataset_sha256: str

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["failed_checks"] = list(self.failed_checks)
        return value


def _reduction(before: float, after: float) -> float:
    return (before - after) / before if before else 0.0


def dataset_fingerprint(records: Iterable[DistillationRecord]) -> str:
    payload = [asdict(record) for record in records]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_distillation(
    records: Iterable[DistillationRecord],
    policy: DistillationPolicy | None = None,
) -> DistillationReport:
    """Aggregate paired observations and apply a deployment policy gate."""

    rows = list(records)
    if not rows:
        raise ValueError("at least one distillation record is required")
    for row in rows:
        row.validate()
    active_policy = policy or DistillationPolicy()
    active_policy.validate()

    teacher_quality = mean(row.teacher_quality for row in rows)
    student_quality = mean(row.student_quality for row in rows)
    teacher_cost = sum(row.teacher_cost for row in rows)
    student_cost = sum(row.student_cost for row in rows)
    teacher_latency = mean(row.teacher_latency_ms for row in rows)
    student_latency = mean(row.student_latency_ms for row in rows)

    quality_retention = student_quality / teacher_quality if teacher_quality else 0.0
    quality_drop = teacher_quality - student_quality
    cost_reduction = _reduction(teacher_cost, student_cost)
    latency_reduction = _reduction(teacher_latency, student_latency)

    failed: list[str] = []
    if quality_retention < active_policy.min_quality_retention:
        failed.append("quality_retention")
    if quality_drop > active_policy.max_student_quality_drop:
        failed.append("student_quality_drop")
    if cost_reduction < active_policy.min_cost_reduction:
        failed.append("cost_reduction")
    if latency_reduction < active_policy.min_latency_reduction:
        failed.append("latency_reduction")

    return DistillationReport(
        sample_count=len(rows),
        teacher_quality=teacher_quality,
        student_quality=student_quality,
        quality_retention=quality_retention,
        quality_drop=quality_drop,
        teacher_cost=teacher_cost,
        student_cost=student_cost,
        cost_reduction=cost_reduction,
        teacher_latency_ms=teacher_latency,
        student_latency_ms=student_latency,
        latency_reduction=latency_reduction,
        passed=not failed,
        failed_checks=tuple(failed),
        dataset_sha256=dataset_fingerprint(rows),
    )


def load_jsonl(path: str | Path) -> list[DistillationRecord]:
    records: list[DistillationRecord] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                records.append(DistillationRecord.from_mapping(value))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid record at line {line_number}: {exc}") from exc
    if not records:
        raise ValueError("distillation dataset is empty")
    return records

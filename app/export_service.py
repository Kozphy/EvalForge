"""Evaluation run report export."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from typing import Any, Literal

from .db import get_conn, row_to_dict, rows_to_dicts

ExportFormat = Literal["json", "jsonl", "csv"]

CSV_FIELDS = [
    "run_id",
    "project_id",
    "result_id",
    "case_id",
    "external_case_id",
    "case_name",
    "prompt",
    "response",
    "expected_label",
    "predicted_label",
    "correct",
    "confidence",
    "needs_human_review",
    "review_status",
    "control_action",
    "release_allowed",
    "groundedness",
    "citation_coverage",
    "retrieval_max_score",
    "reviewer_final_label",
    "reviewer_comment",
    "grader_provider",
    "model",
    "prompt_version",
    "retrieval_method",
    "retrieval_top_k",
    "evidence_threshold",
    "rule_set_version",
    "evaluated_at",
    "deterministic_findings",
    "retrieved_evidence_ids",
    "claim_verdicts",
    "control_findings",
]


def _latest_decision(decisions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not decisions:
        return None
    return sorted(decisions, key=lambda item: item.get("updated_at") or item.get("created_at") or "")[-1]


def _serialize_result(run: dict[str, Any], result: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    config = run.get("config") or {}
    expected = result.get("expected_label")
    predicted = result.get("severity")
    correct: bool | None
    if expected is None:
        correct = None
    else:
        correct = expected == predicted

    evidence = result.get("evidence") or []
    claims = result.get("claims") or []
    findings = result.get("rule_findings") or []
    controls = result.get("controls") or {}
    latest = _latest_decision(decisions)
    adjudicated = next((d for d in decisions if d.get("status") == "ADJUDICATED"), None)
    final_decision = adjudicated or latest

    return {
        "run_id": run["id"],
        "project_id": run["project_id"],
        "result_id": result["id"],
        "case_id": result["case_id"],
        "external_case_id": result.get("external_case_id"),
        "case_name": result.get("case_name"),
        "prompt": result.get("prompt"),
        "response": result.get("response"),
        "expected_label": expected,
        "predicted_label": predicted,
        "correct": correct,
        "confidence": result.get("confidence"),
        "needs_human_review": bool(result.get("needs_human_review")),
        "review_status": result.get("review_status"),
        "human_review_flag": bool(result.get("needs_human_review")),
        "control_action": controls.get("action"),
        "release_allowed": controls.get("release_allowed"),
        "groundedness": controls.get("groundedness"),
        "citation_coverage": controls.get("citation_coverage"),
        "retrieval_max_score": controls.get("retrieval_max_score"),
        "control_findings": controls.get("findings") or [],
        "controls": controls,
        "deterministic_findings": findings,
        "retrieved_evidence_ids": [item.get("chunk_id") for item in evidence if isinstance(item, dict)],
        "retrieval_context": [item.get("text") for item in evidence if isinstance(item, dict)],
        "claim_verdicts": claims,
        "grader_provider": run.get("provider"),
        "model": run.get("model"),
        "prompt_version": config.get("prompt_version"),
        "retrieval_method": config.get("retrieval_method"),
        "retrieval_top_k": config.get("retrieval_top_k"),
        "evidence_threshold": config.get("evidence_threshold"),
        "rule_set_version": config.get("rule_set_version"),
        "evaluation_timestamp": result.get("created_at") or run.get("completed_at") or run.get("created_at"),
        "evaluated_at": result.get("created_at") or run.get("completed_at") or run.get("created_at"),
        "reviewer_final_label": (final_decision or {}).get("final_label") or result.get("final_label"),
        "reviewer_comment": (final_decision or {}).get("comment"),
        "config": config,
        "verdict": result.get("verdict"),
        "reason": result.get("reason"),
    }


def load_export_rows(
    run_id: int,
    *,
    review_required: bool | None = None,
    predicted_label: str | None = None,
    incorrect_only: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with get_conn() as conn:
        run = row_to_dict(conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
        if run is None:
            raise LookupError("Run not found")

        rows = conn.execute(
            """
            SELECT results.*,
                   eval_cases.name AS case_name,
                   eval_cases.prompt,
                   eval_cases.response,
                   eval_cases.expected_label,
                   eval_cases.external_case_id
            FROM results
            JOIN eval_cases ON eval_cases.id = results.case_id
            WHERE results.run_id = ?
            ORDER BY results.id
            """,
            (run_id,),
        ).fetchall()
        results = rows_to_dicts(rows)
        decisions_by_result: dict[int, list[dict[str, Any]]] = {}
        if results:
            result_ids = [int(item["id"]) for item in results]
            placeholders = ",".join("?" for _ in result_ids)
            decision_rows = conn.execute(
                f"""
                SELECT * FROM review_decisions
                WHERE result_id IN ({placeholders})
                ORDER BY id
                """,
                result_ids,
            ).fetchall()
            for decision in rows_to_dicts(decision_rows):
                decisions_by_result.setdefault(int(decision["result_id"]), []).append(decision)

    exported: list[dict[str, Any]] = []
    for result in results:
        if review_required is True and not result.get("needs_human_review"):
            continue
        if review_required is False and result.get("needs_human_review"):
            continue
        if predicted_label and result.get("severity") != predicted_label:
            continue
        row = _serialize_result(run, result, decisions_by_result.get(int(result["id"]), []))
        if incorrect_only and row.get("correct") is not False:
            continue
        exported.append(row)
    return run, exported


def export_run_json(run: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    payload = {
        "run_id": run["id"],
        "project_id": run["project_id"],
        "provider": run.get("provider"),
        "model": run.get("model"),
        "status": run.get("status"),
        "metrics": run.get("metrics") or {},
        "config": run.get("config") or {},
        "created_at": run.get("created_at"),
        "completed_at": run.get("completed_at"),
        "results": rows,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def iter_export_jsonl(rows: list[dict[str, Any]]) -> Iterator[str]:
    for row in rows:
        yield json.dumps(row, ensure_ascii=False) + "\n"


def export_run_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        flat = dict(row)
        flat["deterministic_findings"] = json.dumps(row.get("deterministic_findings") or [], ensure_ascii=False)
        flat["retrieved_evidence_ids"] = json.dumps(row.get("retrieved_evidence_ids") or [], ensure_ascii=False)
        flat["claim_verdicts"] = json.dumps(row.get("claim_verdicts") or [], ensure_ascii=False)
        flat["control_findings"] = json.dumps(row.get("control_findings") or [], ensure_ascii=False)
        writer.writerow({key: flat.get(key) for key in CSV_FIELDS})
    return buffer.getvalue()


def content_type_for(fmt: ExportFormat) -> str:
    if fmt == "json":
        return "application/json"
    if fmt == "jsonl":
        return "application/x-ndjson"
    return "text/csv"


def filename_for(run_id: int, fmt: ExportFormat) -> str:
    return f"evalforge-run-{run_id}.{fmt}"

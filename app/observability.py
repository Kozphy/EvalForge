"""Local-first trace events for evaluation runs.

Trace events are stored in SQLite and can optionally be mirrored to JSONL through
``EVAL_TRACE_JSONL_PATH``. The format is intentionally vendor-neutral so later
adapters can forward it to Phoenix, Langfuse, or OpenTelemetry without coupling
the core runtime to a hosted service.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import get_conn, rows_to_dicts


def utc_now() -> str:
    """Return the current UTC timestamp in ISO 8601 format.

    Returns:
        ISO 8601 formatted UTC timestamp string.
    """
    return datetime.now(timezone.utc).isoformat()


def record_trace_event(
    run_id: int,
    *,
    stage: str,
    status: str,
    payload: dict[str, Any] | None = None,
    result_id: int | None = None,
) -> dict[str, Any]:
    """Record a trace event for an evaluation run.

    Events are stored in SQLite and optionally mirrored to a JSONL file
    if EVAL_TRACE_JSONL_PATH is set. The format is vendor-neutral for
    future integration with observability platforms.

    Args:
        run_id: Database ID of the evaluation run.
        stage: Evaluation stage (e.g., "run", "retrieval", "grader", "controls").
        status: Status of the stage (e.g., "started", "completed", "failed").
        payload: Optional structured data about the event.
        result_id: Optional database ID of the specific result.

    Returns:
        The recorded event dict including the generated ID.
    """
    event = {
        "run_id": run_id,
        "result_id": result_id,
        "stage": stage,
        "status": status,
        "payload": payload or {},
        "created_at": utc_now(),
    }
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO trace_events(
                run_id, result_id, stage, status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                result_id,
                stage,
                status,
                json.dumps(event["payload"], ensure_ascii=False),
                event["created_at"],
            ),
        )
        event["id"] = int(cursor.lastrowid)

    jsonl_path = os.getenv("EVAL_TRACE_JSONL_PATH")
    if jsonl_path:
        path = Path(jsonl_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def list_trace_events(run_id: int) -> list[dict[str, Any]]:
    """List all trace events for a given run.

    Args:
        run_id: Database ID of the evaluation run.

    Returns:
        List of trace event dicts ordered by ID.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trace_events WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
    return rows_to_dicts(rows)

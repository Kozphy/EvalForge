from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from . import service
from .db import get_conn, row_to_dict, rows_to_dicts
from .schemas import RunCreate

router = APIRouter(prefix="/api", tags=["async-runs"])

JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_async_job_schema() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS async_run_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                run_id INTEGER,
                status TEXT NOT NULL,
                config_json TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_async_run_jobs_project_id
                ON async_run_jobs(project_id);
            CREATE INDEX IF NOT EXISTS idx_async_run_jobs_status
                ON async_run_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_async_run_jobs_created_at
                ON async_run_jobs(created_at);
            """
        )


def _job_to_dict(row: Any) -> dict[str, Any] | None:
    item = row_to_dict(row)
    if item is not None and "cancel_requested" in item:
        item["cancel_requested"] = bool(item["cancel_requested"])
    return item


def get_job(job_id: int) -> dict[str, Any] | None:
    ensure_async_job_schema()
    with get_conn() as conn:
        return _job_to_dict(
            conn.execute("SELECT * FROM async_run_jobs WHERE id = ?", (job_id,)).fetchone()
        )


def list_jobs(
    *,
    project_id: int | None = None,
    status: JobStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    ensure_async_job_schema()
    clauses: list[str] = []
    params: list[Any] = []
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(project_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM async_run_jobs
            {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        ).fetchall()
    jobs = rows_to_dicts(rows)
    for job in jobs:
        job["cancel_requested"] = bool(job.get("cancel_requested"))
    return jobs


def enqueue_job(project_id: int, config: RunCreate) -> dict[str, Any]:
    ensure_async_job_schema()
    if service.get_project(project_id) is None:
        raise LookupError("Project not found")
    if not service.list_cases(project_id):
        raise ValueError("Add at least one evaluation case before queueing an evaluation")

    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO async_run_jobs(project_id, status, config_json)
            VALUES (?, 'queued', ?)
            """,
            (project_id, config.model_dump_json()),
        )
        job_id = int(cursor.lastrowid)
    job = get_job(job_id)
    assert job is not None
    return job


def process_job(job_id: int) -> None:
    ensure_async_job_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM async_run_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        job = _job_to_dict(row)
        if job is None or job["status"] != "queued":
            return
        if job["cancel_requested"]:
            conn.execute(
                """
                UPDATE async_run_jobs
                SET status='cancelled', completed_at=?, updated_at=?
                WHERE id=?
                """,
                (utc_now(), utc_now(), job_id),
            )
            return
        conn.execute(
            """
            UPDATE async_run_jobs
            SET status='running', started_at=?, updated_at=?,
                attempt_count=attempt_count + 1, error=NULL
            WHERE id=?
            """,
            (utc_now(), utc_now(), job_id),
        )

    try:
        config = RunCreate.model_validate(job["config"])
        run = service.execute_run(int(job["project_id"]), config)
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE async_run_jobs
                SET status='completed', run_id=?, completed_at=?, updated_at=?
                WHERE id=?
                """,
                (run.get("id"), utc_now(), utc_now(), job_id),
            )
    except Exception as exc:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE async_run_jobs
                SET status='failed', error=?, completed_at=?, updated_at=?
                WHERE id=?
                """,
                (str(exc), utc_now(), utc_now(), job_id),
            )


def cancel_job(job_id: int) -> dict[str, Any]:
    ensure_async_job_schema()
    job = get_job(job_id)
    if job is None:
        raise LookupError("Async run job not found")
    if job["status"] in {"completed", "failed", "cancelled"}:
        raise ValueError(f"Cannot cancel a {job['status']} job")
    if job["status"] == "running":
        raise ValueError("Running jobs cannot yet be interrupted safely")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE async_run_jobs
            SET cancel_requested=1, status='cancelled', completed_at=?, updated_at=?
            WHERE id=?
            """,
            (utc_now(), utc_now(), job_id),
        )
    cancelled = get_job(job_id)
    assert cancelled is not None
    return cancelled


def retry_job(job_id: int) -> dict[str, Any]:
    ensure_async_job_schema()
    job = get_job(job_id)
    if job is None:
        raise LookupError("Async run job not found")
    if job["status"] not in {"failed", "cancelled"}:
        raise ValueError("Only failed or cancelled jobs can be retried")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE async_run_jobs
            SET status='queued', run_id=NULL, cancel_requested=0, error=NULL,
                started_at=NULL, completed_at=NULL, updated_at=?
            WHERE id=?
            """,
            (utc_now(), job_id),
        )
    retried = get_job(job_id)
    assert retried is not None
    return retried


@router.post("/projects/{project_id}/runs/async", status_code=202)
def create_async_run(
    project_id: int,
    payload: RunCreate,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    try:
        job = enqueue_job(project_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(process_job, int(job["id"]))
    return job


@router.get("/run-jobs")
def get_async_jobs(
    project_id: int | None = None,
    status: JobStatus | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return list_jobs(project_id=project_id, status=status, limit=limit, offset=offset)


@router.get("/run-jobs/{job_id}")
def get_async_job(job_id: int) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Async run job not found")
    if job.get("run_id") is not None:
        job["run"] = service.get_run(int(job["run_id"]))
    return job


@router.post("/run-jobs/{job_id}/cancel")
def request_job_cancellation(job_id: int) -> dict[str, Any]:
    try:
        return cancel_job(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/run-jobs/{job_id}/retry", status_code=202)
def retry_async_job(job_id: int, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        job = retry_job(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(process_job, job_id)
    return job

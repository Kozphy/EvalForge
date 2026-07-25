from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import export_service, import_service, review_service, service
from .async_runs import ensure_async_job_schema, router as async_runs_router
from .db import init_db
from .schemas import (
    AdjudicationCreate,
    DocumentCreate,
    EvalCaseBatchCreate,
    EvalCaseCreate,
    ProjectCreate,
    ReviewDecisionCreate,
    RunCreate,
)
from .version import APP_VERSION

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    ensure_async_job_schema()
    yield


app = FastAPI(
    title="EvalForge",
    version=APP_VERSION,
    description="Local-first AI evaluation engineering platform",
    lifespan=lifespan,
)
app.include_router(async_runs_router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    return service.list_projects()


@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    return service.create_project(payload.name, payload.description)


@app.get("/api/projects/{project_id}")
def get_project(project_id: int) -> dict[str, Any]:
    project = service.get_project_detail(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.post("/api/projects/{project_id}/documents", status_code=201)
def add_document(project_id: int, payload: DocumentCreate) -> dict[str, Any]:
    try:
        return service.add_document(project_id, payload.title, payload.content)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/cases", status_code=201)
def add_case(project_id: int, payload: EvalCaseCreate) -> dict[str, Any]:
    try:
        return service.add_case(project_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/cases/batch", status_code=201)
def add_cases_batch(project_id: int, payload: EvalCaseBatchCreate) -> dict[str, Any]:
    try:
        created = service.add_cases_batch(project_id, payload.cases)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"count": len(created), "cases": created}


@app.post("/api/projects/{project_id}/cases/import")
async def import_cases(
    project_id: int,
    file: UploadFile = File(...),
    dry_run: bool = Form(default=False),
    atomic: bool = Form(default=True),
) -> dict[str, Any]:
    try:
        result = import_service.import_cases_from_upload(
            project_id,
            filename=file.filename or "upload",
            file_obj=file.file,
            dry_run=dry_run,
            atomic=atomic,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/api/projects/{project_id}/cases/import-jsonl")
async def import_cases_jsonl(
    project_id: int,
    file: UploadFile = File(...),
    dry_run: bool = Form(default=False),
    atomic: bool = Form(default=True),
) -> dict[str, Any]:
    name = file.filename or "upload.jsonl"
    if not name.lower().endswith(".jsonl"):
        raise HTTPException(status_code=400, detail="Expected a .jsonl file.")
    return await import_cases(project_id, file=file, dry_run=dry_run, atomic=atomic)


@app.post("/api/projects/{project_id}/cases/import-csv")
async def import_cases_csv(
    project_id: int,
    file: UploadFile = File(...),
    dry_run: bool = Form(default=False),
    atomic: bool = Form(default=True),
) -> dict[str, Any]:
    name = file.filename or "upload.csv"
    if not name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Expected a .csv file.")
    return await import_cases(project_id, file=file, dry_run=dry_run, atomic=atomic)


@app.post("/api/projects/{project_id}/seed", status_code=201)
def seed_project(project_id: int) -> dict[str, Any]:
    try:
        return service.seed_project(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Sample data missing: {exc}") from exc


@app.post("/api/projects/{project_id}/runs", status_code=201)
def create_run(project_id: int, payload: RunCreate) -> dict[str, Any]:
    try:
        return service.execute_run(project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/runs/{run_id}/export")
def export_run(
    run_id: int,
    format: Literal["json", "jsonl", "csv"] = Query(default="json"),
    review_required: bool | None = Query(default=None),
    predicted_label: str | None = Query(default=None),
    incorrect_only: bool = Query(default=False),
) -> StreamingResponse:
    try:
        run, rows = export_service.load_export_rows(
            run_id,
            review_required=review_required,
            predicted_label=predicted_label,
            incorrect_only=incorrect_only,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filename = export_service.filename_for(run_id, format)
    media_type = export_service.content_type_for(format)

    if format == "json":
        body = export_service.export_run_json(run, rows)
        return StreamingResponse(
            iter([body]),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if format == "jsonl":
        return StreamingResponse(
            export_service.iter_export_jsonl(rows),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    body = export_service.export_run_csv(rows)
    return StreamingResponse(
        iter([body]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reviews")
def list_reviews(
    project_id: int | None = None,
    run_id: int | None = None,
    predicted_label: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    review_status: str | None = None,
    needs_human_review: bool | None = True,
    sort_by: str = "confidence",
    sort_dir: str = "asc",
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return review_service.list_reviews(
        project_id=project_id,
        run_id=run_id,
        predicted_label=predicted_label,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        review_status=review_status,
        needs_human_review=needs_human_review,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@app.get("/api/reviews/{result_id}")
def get_review(result_id: int) -> dict[str, Any]:
    detail = review_service.get_review_detail(result_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return detail


@app.post("/api/reviews/{result_id}/decisions", status_code=201)
def submit_review_decision(result_id: int, payload: ReviewDecisionCreate) -> dict[str, Any]:
    try:
        return review_service.submit_decision(result_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/reviews/{result_id}/adjudicate", status_code=201)
def adjudicate_review(result_id: int, payload: AdjudicationCreate) -> dict[str, Any]:
    try:
        return review_service.adjudicate(result_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

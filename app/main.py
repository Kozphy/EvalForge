from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import export_service, import_service, review_service, service
from .client_api import ApiTargetConfig
from .control_plane import api as control_plane_api
from .control_plane import operator_service
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
    yield


app = FastAPI(
    title="EvalForge",
    version=APP_VERSION,
    description="Evaluation Control Plane for LLM, RAG, and Agent systems (local-first workbench + orchestrated backends)",
    lifespan=lifespan,
)


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


@app.put("/api/projects/{project_id}/api-target")
def put_api_target(project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        target = ApiTargetConfig.model_validate(payload)
        return service.set_api_target(project_id, target)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        for err in exc.errors():
            err_type = str(err.get("type", ""))
            if err_type.startswith("greater_than") or err_type.startswith("less_than"):
                raise HTTPException(status_code=422, detail=exc.errors()) from exc
        messages: list[str] = []
        for err in exc.errors():
            msg = str(err.get("msg", ""))
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, ") :]
            messages.append(msg)
        raise HTTPException(status_code=400, detail="; ".join(messages) or "Invalid API target") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.post("/api/control-plane/experiments/run")
def control_plane_run_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a control-plane experiment (demo adapters by default)."""
    demo = bool(payload.get("demo", True))
    try:
        return control_plane_api.run_control_plane_experiment(payload, demo=demo)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/control-plane/evaluators")
def control_plane_evaluators() -> list[dict[str, Any]]:
    return control_plane_api.list_evaluators()


@app.get("/api/control-plane/evaluators/health")
def control_plane_evaluators_health() -> list[dict[str, Any]]:
    return control_plane_api.list_evaluators()


@app.get("/api/control-plane/runs/{run_id}")
def control_plane_get_run(run_id: str) -> dict[str, Any]:
    run = control_plane_api.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Control-plane run not found")
    return run


@app.get("/api/control-plane/baselines")
def control_plane_baselines() -> list[dict[str, Any]]:
    return control_plane_api.list_baselines()


@app.get("/api/control-plane/evidence/{experiment_id}")
def control_plane_evidence(experiment_id: str) -> list[dict[str, Any]]:
    return control_plane_api.export_evidence(experiment_id)


@app.post("/api/operator/demo/reset")
def operator_demo_reset() -> dict[str, Any]:
    world = operator_service.reset_demo()
    return {"status": "ok", "source": "demo_fixture", "run_id": world["runs"][0]["run_id"]}


@app.get("/api/operator/overview")
def operator_overview() -> dict[str, Any]:
    return operator_service.get_overview()


@app.get("/api/operator/runs")
def operator_list_runs(
    model: str | None = None,
    dataset: str | None = None,
    result: str | None = None,
    policy_decision: str | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    return operator_service.list_runs(
        {
            "model": model,
            "dataset": dataset,
            "result": result,
            "policy_decision": policy_decision,
            "environment": environment,
        }
    )


@app.get("/api/operator/runs/{run_id}")
def operator_get_run(run_id: str) -> dict[str, Any]:
    run = operator_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/operator/baselines")
def operator_baselines() -> list[dict[str, Any]]:
    return operator_service.list_baselines()


@app.get("/api/operator/regressions")
def operator_regressions(run_id: str | None = None) -> dict[str, Any]:
    return operator_service.get_regressions(run_id)


@app.get("/api/operator/policy")
def operator_policy(run_id: str | None = None) -> dict[str, Any]:
    return operator_service.get_policy(run_id)


@app.get("/api/operator/evidence")
def operator_evidence(run_id: str | None = None, experiment_id: str | None = None) -> list[dict[str, Any]]:
    return operator_service.list_evidence(run_id=run_id, experiment_id=experiment_id)


@app.get("/api/operator/approvals")
def operator_approvals() -> list[dict[str, Any]]:
    return operator_service.list_approvals()


@app.post("/api/operator/approvals/{approval_id}/decision")
def operator_approval_decision(approval_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return operator_service.decide_approval(
            approval_id,
            outcome=str(payload.get("outcome") or ""),
            reviewer=str(payload.get("reviewer") or ""),
            comment=payload.get("comment"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/operator/audit")
def operator_audit(
    actor: str | None = None,
    event_type: str | None = None,
    entity: str | None = None,
) -> list[dict[str, Any]]:
    return operator_service.list_audit({"actor": actor, "event_type": event_type, "entity": entity})


@app.get("/api/operator/research")
def operator_research() -> dict[str, Any]:
    return operator_service.get_research()


@app.get("/api/operator/settings")
def operator_settings() -> dict[str, Any]:
    return operator_service.get_settings()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/workbench")
def workbench() -> FileResponse:
    return FileResponse(STATIC_DIR / "workbench.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

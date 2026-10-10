from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import observability
from .client_api import (
    ApiCallResult,
    ApiTargetConfig,
    build_http_client,
    call_client_api,
    redact_secrets,
)
from .config import build_grader_config
from .controls import ControlPolicy, evaluate_controls
from .db import get_conn, row_to_dict, rows_to_dicts
from .graders import calculate_metrics, heuristic_grade, openai_grade
from .retrieval import retrieve
from .schemas import EvalCaseCreate, GraderOutput, RequirementSpec, ReviewStatus, RunCreate

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace(
    enabled: bool,
    run_id: int,
    *,
    stage: str,
    status: str,
    payload: dict[str, Any] | None = None,
    result_id: int | None = None,
) -> None:
    """Record a trace event, swallowing all errors so tracing never fails evaluation.

    Args:
        enabled: Whether tracing is active for this run.
        run_id: Database ID of the evaluation run.
        stage: Evaluation stage (e.g. "run", "retrieval", "grader", "controls").
        status: Stage status (e.g. "started", "completed", "failed", or a control action).
        payload: Optional structured data to attach to the event.
        result_id: Optional database ID of the specific result being traced.
    """
    if not enabled:
        return
    try:
        observability.record_trace_event(
            run_id,
            stage=stage,
            status=status,
            payload=payload,
            result_id=result_id,
        )
    except Exception:
        pass


def get_project(project_id: int) -> dict | None:
    with get_conn() as conn:
        return row_to_dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())


def list_projects() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT projects.*,
                   (SELECT COUNT(*) FROM documents d WHERE d.project_id = projects.id) AS document_count,
                   (SELECT COUNT(*) FROM eval_cases c WHERE c.project_id = projects.id) AS case_count,
                   (SELECT COUNT(*) FROM runs r WHERE r.project_id = projects.id) AS run_count
            FROM projects
            ORDER BY projects.id DESC
            """
        ).fetchall()
        return rows_to_dicts(rows)


def create_project(name: str, description: str = "") -> dict:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO projects(name, description) VALUES (?, ?)",
            (name, description),
        )
        project_id = int(cursor.lastrowid)
    project = get_project(project_id)
    assert project is not None
    return project


def get_project_detail(project_id: int) -> dict | None:
    project = get_project(project_id)
    if project is None:
        return None
    with get_conn() as conn:
        runs = rows_to_dicts(
            conn.execute(
                "SELECT * FROM runs WHERE project_id=? ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        )
    project["documents"] = list_documents(project_id)
    project["cases"] = list_cases(project_id)
    project["runs"] = runs
    # Ensure key exists even when column is NULL on older rows.
    if "api_target" not in project:
        project["api_target"] = None
    return project


def get_api_target(project_id: int) -> ApiTargetConfig | None:
    project = get_project(project_id)
    if project is None:
        raise LookupError("Project not found")
    raw = project.get("api_target")
    if not raw:
        return None
    return ApiTargetConfig.model_validate(raw)


def set_api_target(project_id: int, target: ApiTargetConfig) -> dict:
    if get_project(project_id) is None:
        raise LookupError("Project not found")
    payload = target.public_dict()
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET api_target_json=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), project_id),
        )
    return payload


def list_documents(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
        return rows_to_dicts(rows)


def add_document(project_id: int, title: str, content: str) -> dict:
    if get_project(project_id) is None:
        raise LookupError("Project not found")
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO documents(project_id, title, content) VALUES (?, ?, ?)",
            (project_id, title, content),
        )
        doc_id = int(cursor.lastrowid)
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    result = row_to_dict(row)
    assert result is not None
    return result


def list_cases(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eval_cases WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
        return rows_to_dicts(rows)


def add_case(project_id: int, case: EvalCaseCreate) -> dict:
    if get_project(project_id) is None:
        raise LookupError("Project not found")
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO eval_cases(
                project_id, name, prompt, response, expected_label,
                requirements_json, metadata_json, external_case_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                case.name,
                case.prompt,
                case.response,
                case.expected_label,
                case.requirements.model_dump_json(),
                json.dumps(case.metadata, ensure_ascii=False),
                case.case_id,
            ),
        )
        case_id = int(cursor.lastrowid)
        row = conn.execute("SELECT * FROM eval_cases WHERE id=?", (case_id,)).fetchone()
    result = row_to_dict(row)
    assert result is not None
    return result


def add_cases_batch(project_id: int, cases: list[EvalCaseCreate]) -> list[dict]:
    if get_project(project_id) is None:
        raise LookupError("Project not found")
    created: list[dict] = []
    with get_conn() as conn:
        for case in cases:
            cursor = conn.execute(
                """
                INSERT INTO eval_cases(
                    project_id, name, prompt, response, expected_label,
                    requirements_json, metadata_json, external_case_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    case.name,
                    case.prompt,
                    case.response,
                    case.expected_label,
                    case.requirements.model_dump_json(),
                    json.dumps(case.metadata, ensure_ascii=False),
                    case.case_id,
                ),
            )
            case_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM eval_cases WHERE id=?", (case_id,)).fetchone()
            created.append(row_to_dict(row) or {})
    return created


def seed_project(project_id: int) -> dict:
    if get_project(project_id) is None:
        raise LookupError("Project not found")

    reference_path = EXAMPLES_DIR / "accounting_reference.md"
    cases_path = EXAMPLES_DIR / "accounting_cases.jsonl"
    reference = reference_path.read_text(encoding="utf-8")
    add_document(project_id, "Accounting reference", reference)

    cases: list[EvalCaseCreate] = []
    for line in cases_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cases.append(EvalCaseCreate.model_validate(json.loads(line)))
    created = add_cases_batch(project_id, cases)
    return {
        "project_id": project_id,
        "documents_added": 1,
        "cases_added": len(created),
        "cases": created,
    }


def validate_requirements_for_run(cases: list[dict]) -> None:
    for case in cases:
        try:
            RequirementSpec.model_validate(case.get("requirements") or {})
        except Exception as exc:
            raise ValueError(
                f"Invalid grader requirements on case {case.get('id')} ({case.get('name')}): {exc}"
            ) from exc


def execute_run(project_id: int, config: RunCreate) -> dict:
    project = get_project(project_id)
    if project is None:
        raise ValueError("Project not found")

    documents = list_documents(project_id)
    cases = list_cases(project_id)
    if not cases:
        raise ValueError("Add at least one evaluation case before running an evaluation")

    validate_requirements_for_run(cases)

    api_target: ApiTargetConfig | None = None
    api_target_public: dict | None = None
    if config.provider == "client_api":
        api_target = get_api_target(project_id)
        if api_target is None:
            raise ValueError("Configure an API target before running the client API provider.")
        api_target_public = api_target.public_dict()

    grader_config = build_grader_config(
        provider=config.provider,
        model=config.model,
        top_k=config.top_k,
        dataset_version=config.dataset_version,
        prompt_version=config.prompt_version,
        system_prompt=config.system_prompt,
        grader_prompt=config.grader_prompt,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
        evidence_threshold=config.evidence_threshold,
        rule_set_version=config.rule_set_version,
        model_version=config.model_version,
        min_groundedness=config.min_groundedness,
        min_citation_coverage=config.min_citation_coverage,
        control_min_confidence=config.control_min_confidence,
        block_on_contradiction=config.block_on_contradiction,
        block_on_invalid_citation=config.block_on_invalid_citation,
        block_on_major_rule_failure=config.block_on_major_rule_failure,
        trace_enabled=config.trace_enabled,
    )
    control_policy = ControlPolicy(
        min_groundedness=config.min_groundedness,
        min_citation_coverage=config.min_citation_coverage,
        min_confidence=config.control_min_confidence,
        block_on_contradiction=config.block_on_contradiction,
        block_on_invalid_citation=config.block_on_invalid_citation,
        block_on_major_rule_failure=config.block_on_major_rule_failure,
    )

    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs(project_id, provider, model, status, config_json)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (
                project_id,
                config.provider,
                config.model,
                grader_config.model_dump_json(),
            ),
        )
        run_id = int(cursor.lastrowid)

    _trace(
        config.trace_enabled,
        run_id,
        stage="run",
        status="started",
        payload={"project_id": project_id, "case_count": len(cases)},
    )

    predicted: list[str] = []
    expected: list[str | None] = []
    control_actions: list[str] = []
    groundedness_values: list[float] = []
    citation_coverage_values: list[float] = []
    http_client = None
    if config.provider == "client_api":
        assert api_target is not None
        http_client = build_http_client(api_target.timeout_seconds)

    try:
        for case in cases:
            requirements = RequirementSpec.model_validate(case.get("requirements") or {})
            api_call_meta: dict[str, Any] | None = None
            response_text = case["response"]

            if config.provider == "client_api":
                assert api_target is not None
                api_result = call_client_api(
                    api_target,
                    case["prompt"],
                    client=http_client,
                )
                api_call_meta = {
                    "response_text": api_result.response_text,
                    "latency_ms": api_result.latency_ms,
                    "http_status": api_result.http_status,
                    "error": api_result.error,
                }
                if api_result.error or not api_result.response_text:
                    output, rule_findings = _api_failure_output(api_result)
                    predicted.append(output.severity)
                    expected.append(case.get("expected_label"))
                    result_id, control_report = _insert_result(
                        run_id=run_id,
                        case=case,
                        output=output,
                        rule_findings=rule_findings,
                        evidence=[],
                        api_call_meta=api_call_meta,
                        control_policy=control_policy,
                    )
                    _trace(
                        config.trace_enabled,
                        run_id,
                        result_id=result_id,
                        stage="grader",
                        status="completed",
                        payload={
                            "case_id": case["id"],
                            "provider": config.provider,
                            "verdict": output.verdict,
                            "severity": output.severity,
                            "confidence": output.confidence,
                            "claim_count": len(output.claims),
                            "failed_rule_count": sum(not item.passed for item in rule_findings),
                        },
                    )
                    if control_report:
                        _trace(
                            config.trace_enabled,
                            run_id,
                            result_id=result_id,
                            stage="controls",
                            status=control_report.action,
                            payload=control_report.model_dump(mode="json"),
                        )
                    continue

                response_text = api_result.response_text
                _update_case_response(int(case["id"]), response_text)

            query = f"{case['prompt']}\n{response_text}"
            evidence = retrieve(query, documents, top_k=config.top_k)
            _trace(
                config.trace_enabled,
                run_id,
                stage="retrieval",
                status="completed",
                payload={
                    "case_id": case["id"],
                    "query_chars": len(query),
                    "top_k": config.top_k,
                    "evidence": [
                        {"chunk_id": item.get("chunk_id"), "score": item.get("score")}
                        for item in evidence
                    ],
                },
            )

            if config.provider == "openai":
                output, rule_findings = openai_grade(
                    case["prompt"], response_text, requirements, evidence, config.model
                )
            else:
                # heuristic and successful client_api paths share the offline grader
                output, rule_findings = heuristic_grade(
                    case["prompt"], response_text, requirements, evidence
                )

            control_report = evaluate_controls(
                output,
                rule_findings,
                evidence,
                control_policy,
            )
            predicted.append(output.severity)
            expected.append(case.get("expected_label"))
            control_actions.append(control_report.action)
            groundedness_values.append(control_report.groundedness)
            citation_coverage_values.append(control_report.citation_coverage)

            result_id, _ = _insert_result(
                run_id=run_id,
                case=case,
                output=output,
                rule_findings=rule_findings,
                evidence=evidence,
                api_call_meta=api_call_meta,
                control_policy=control_policy,
            )

            _trace(
                config.trace_enabled,
                run_id,
                result_id=result_id,
                stage="grader",
                status="completed",
                payload={
                    "case_id": case["id"],
                    "provider": config.provider,
                    "verdict": output.verdict,
                    "severity": output.severity,
                    "confidence": output.confidence,
                    "claim_count": len(output.claims),
                    "failed_rule_count": sum(not item.passed for item in rule_findings),
                },
            )
            _trace(
                config.trace_enabled,
                run_id,
                result_id=result_id,
                stage="controls",
                status=control_report.action,
                payload=control_report.model_dump(mode="json"),
            )

        metrics = calculate_metrics(expected, predicted)
        metrics["case_count"] = len(cases)
        metrics["human_review_count"] = _human_review_count(run_id)
        actions = Counter(control_actions)
        metrics["controls"] = {
            "allow_count": actions.get("allow", 0),
            "review_count": actions.get("review", 0),
            "block_count": actions.get("block", 0),
            "release_rate": round(actions.get("allow", 0) / len(cases), 4) if len(cases) > 0 else 0,
            "average_groundedness": round(
                sum(groundedness_values) / len(groundedness_values), 4
            ) if groundedness_values else 0,
            "average_citation_coverage": round(
                sum(citation_coverage_values) / len(citation_coverage_values), 4
            ) if citation_coverage_values else 0,
        }
        if config.provider == "client_api":
            metrics["api_error_count"] = _api_error_count(run_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE runs SET status='completed', metrics_json=?, completed_at=? WHERE id=?",
                (json.dumps(metrics), utc_now(), run_id),
            )
        _trace(
            config.trace_enabled,
            run_id,
            stage="run",
            status="completed",
            payload={"metrics": metrics},
        )
    except Exception as exc:
        message = str(exc)
        if api_target and api_target.auth_env_var:
            secret = os.getenv(api_target.auth_env_var)
            if secret:
                message = redact_secrets(message, [secret])
        with get_conn() as conn:
            conn.execute(
                "UPDATE runs SET status='failed', metrics_json=?, completed_at=? WHERE id=?",
                (json.dumps({"error": message}), utc_now(), run_id),
            )
        _trace(
            config.trace_enabled,
            run_id,
            stage="run",
            status="failed",
            payload={"error": str(exc)},
        )
        if message != str(exc):
            raise RuntimeError(message) from exc
        raise
    finally:
        if http_client is not None:
            http_client.close()

    return get_run(run_id) or {"id": run_id, "status": "completed"}


def _api_failure_output(api_result: ApiCallResult) -> tuple[GraderOutput, list]:
    reason = api_result.error or "Client API call failed."
    output = GraderOutput(
        verdict="fail",
        severity="major",
        score=0.0,
        confidence=0.0,
        reason=reason,
        claims=[],
        needs_human_review=True,
    )
    return output, []


def _update_case_response(case_id: int, response: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE eval_cases SET response=? WHERE id=?",
            (response, case_id),
        )


def _insert_result(
    *,
    run_id: int,
    case: dict,
    output: GraderOutput,
    rule_findings: list,
    evidence: list,
    api_call_meta: dict[str, Any] | None,
    control_policy: ControlPolicy | None = None,
) -> tuple[int, ControlPolicy | None]:
    """Persist a single grader result to the database.

    If a control policy is provided, evaluates release controls and stores
    the control report alongside the result. The needs_human_review flag is
    set if either the grader or controls require it.

    Args:
        run_id: Database ID of the evaluation run.
        case: Eval case dict with at minimum an "id" key.
        output: Grader output including verdict, severity, claims, and confidence.
        rule_findings: List of deterministic rule check results.
        evidence: Retrieved evidence chunks.
        api_call_meta: Optional metadata from a client API call.
        control_policy: Optional control policy to evaluate release decisions.

    Returns:
        Tuple of (result_id, control_report). control_report is None if no policy
        was provided.
    """
    needs_review = bool(output.needs_human_review)
    review_status = ReviewStatus.PENDING.value
    raw = output.model_dump(mode="json")
    if api_call_meta is not None:
        raw["api_call"] = api_call_meta
    
    # Evaluate controls if policy is provided
    control_report = None
    if control_policy is not None:
        control_report = evaluate_controls(
            output,
            rule_findings,
            evidence,
            control_policy,
        )
        raw["controls"] = control_report.model_dump(mode="json")
        needs_review = bool(needs_review or control_report.needs_human_review)
    
    with get_conn() as conn:
        if control_report is not None:
            conn.execute(
                """
                INSERT INTO results(
                    run_id, case_id, verdict, severity, score, confidence, reason,
                    evidence_json, claims_json, rule_findings_json, controls_json,
                    needs_human_review, review_status, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    case["id"],
                    output.verdict,
                    output.severity,
                    output.score,
                    output.confidence,
                    output.reason,
                    json.dumps(evidence, ensure_ascii=False),
                    json.dumps(
                        [item.model_dump(mode="json") for item in output.claims],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        [item.model_dump(mode="json") for item in rule_findings],
                        ensure_ascii=False,
                    ),
                    control_report.model_dump_json(),
                    int(needs_review),
                    review_status,
                    json.dumps(raw, ensure_ascii=False),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO results(
                    run_id, case_id, verdict, severity, score, confidence, reason,
                    evidence_json, claims_json, rule_findings_json,
                    needs_human_review, review_status, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    case["id"],
                    output.verdict,
                    output.severity,
                    output.score,
                    output.confidence,
                    output.reason,
                    json.dumps(evidence, ensure_ascii=False),
                    json.dumps(
                        [item.model_dump(mode="json") for item in output.claims],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        [item.model_dump(mode="json") for item in rule_findings],
                        ensure_ascii=False,
                    ),
                    int(needs_review),
                    review_status,
                    json.dumps(raw, ensure_ascii=False),
                ),
            )
        result_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    return result_id, control_report


def _api_error_count(run_id: int) -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT raw_json FROM results WHERE run_id=?",
            (run_id,),
        ).fetchall()
    count = 0
    for row in rows:
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except json.JSONDecodeError:
            continue
        api_call = raw.get("api_call") or {}
        if api_call.get("error"):
            count += 1
    return count


def _human_review_count(run_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM results WHERE run_id=? AND needs_human_review=1",
            (run_id,),
        ).fetchone()
        return int(row["count"])


def get_run(run_id: int) -> dict | None:
    with get_conn() as conn:
        run = row_to_dict(conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
        if run is None:
            return None
        rows = conn.execute(
            """
            SELECT results.*, eval_cases.name AS case_name, eval_cases.prompt,
                   eval_cases.response, eval_cases.expected_label,
                   eval_cases.external_case_id
            FROM results
            JOIN eval_cases ON eval_cases.id = results.case_id
            WHERE results.run_id = ?
            ORDER BY results.id
            """,
            (run_id,),
        ).fetchall()
        run["results"] = rows_to_dicts(rows)
        return run

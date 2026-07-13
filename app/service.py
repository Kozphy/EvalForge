from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import build_grader_config
from .db import get_conn, row_to_dict, rows_to_dicts
from .graders import calculate_metrics, heuristic_grade, openai_grade
from .retrieval import retrieve
from .schemas import EvalCaseCreate, RequirementSpec, ReviewStatus, RunCreate

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    return project


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

    predicted: list[str] = []
    expected: list[str | None] = []

    try:
        for case in cases:
            requirements = RequirementSpec.model_validate(case.get("requirements") or {})
            query = f"{case['prompt']}\n{case['response']}"
            evidence = retrieve(query, documents, top_k=config.top_k)

            if config.provider == "openai":
                output, rule_findings = openai_grade(
                    case["prompt"], case["response"], requirements, evidence, config.model
                )
            else:
                output, rule_findings = heuristic_grade(
                    case["prompt"], case["response"], requirements, evidence
                )

            predicted.append(output.severity)
            expected.append(case.get("expected_label"))
            raw = output.model_dump(mode="json")
            needs_review = bool(output.needs_human_review)
            review_status = (
                ReviewStatus.PENDING.value if needs_review else ReviewStatus.PENDING.value
            )

            with get_conn() as conn:
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
                        json.dumps([item.model_dump(mode="json") for item in output.claims], ensure_ascii=False),
                        json.dumps([item.model_dump(mode="json") for item in rule_findings], ensure_ascii=False),
                        int(needs_review),
                        review_status,
                        json.dumps(raw, ensure_ascii=False),
                    ),
                )

        metrics = calculate_metrics(expected, predicted)
        metrics["case_count"] = len(cases)
        metrics["human_review_count"] = _human_review_count(run_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE runs SET status='completed', metrics_json=?, completed_at=? WHERE id=?",
                (json.dumps(metrics), utc_now(), run_id),
            )
    except Exception as exc:
        with get_conn() as conn:
            conn.execute(
                "UPDATE runs SET status='failed', metrics_json=?, completed_at=? WHERE id=?",
                (json.dumps({"error": str(exc)}), utc_now(), run_id),
            )
        raise

    return get_run(run_id) or {"id": run_id, "status": "completed"}


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

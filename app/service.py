from __future__ import annotations

import json
from datetime import datetime, timezone

from .db import get_conn, row_to_dict, rows_to_dicts
from .graders import calculate_metrics, heuristic_grade, openai_grade
from .retrieval import retrieve
from .schemas import RequirementSpec, RunCreate


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_project(project_id: int) -> dict | None:
    with get_conn() as conn:
        return row_to_dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())


def list_documents(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
        return rows_to_dicts(rows)


def list_cases(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM eval_cases WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
        return rows_to_dicts(rows)


def execute_run(project_id: int, config: RunCreate) -> dict:
    project = get_project(project_id)
    if project is None:
        raise ValueError("Project not found")

    documents = list_documents(project_id)
    cases = list_cases(project_id)
    if not cases:
        raise ValueError("Add at least one evaluation case before running an evaluation")

    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO runs(project_id, provider, model, status) VALUES (?, ?, ?, 'running')",
            (project_id, config.provider, config.model),
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

            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO results(
                        run_id, case_id, verdict, severity, score, confidence, reason,
                        evidence_json, claims_json, rule_findings_json,
                        needs_human_review, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        int(output.needs_human_review),
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
                   eval_cases.response, eval_cases.expected_label
            FROM results
            JOIN eval_cases ON eval_cases.id = results.case_id
            WHERE results.run_id = ?
            ORDER BY results.id
            """,
            (run_id,),
        ).fetchall()
        run["results"] = rows_to_dicts(rows)
        return run

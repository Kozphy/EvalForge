"""Human review and adjudication workflow."""

from __future__ import annotations

from typing import Any

from .db import get_conn, row_to_dict, rows_to_dicts
from .schemas import AdjudicationCreate, ReviewDecisionCreate, ReviewStatus
from .service import utc_now


def _get_result(conn: Any, result_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT results.*,
               eval_cases.name AS case_name,
               eval_cases.prompt,
               eval_cases.response,
               eval_cases.expected_label,
               eval_cases.external_case_id,
               runs.project_id,
               runs.provider,
               runs.model,
               runs.config_json
        FROM results
        JOIN eval_cases ON eval_cases.id = results.case_id
        JOIN runs ON runs.id = results.run_id
        WHERE results.id = ?
        """,
        (result_id,),
    ).fetchone()
    return row_to_dict(row)


def list_reviews(
    *,
    project_id: int | None = None,
    run_id: int | None = None,
    predicted_label: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    review_status: str | None = None,
    needs_human_review: bool | None = True,
    sort_by: str = "confidence",
    sort_dir: str = "asc",
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []

    if needs_human_review is True:
        clauses.append("results.needs_human_review = 1")
    elif needs_human_review is False:
        clauses.append("results.needs_human_review = 0")

    if project_id is not None:
        clauses.append("runs.project_id = ?")
        params.append(project_id)
    if run_id is not None:
        clauses.append("results.run_id = ?")
        params.append(run_id)
    if predicted_label:
        clauses.append("results.severity = ?")
        params.append(predicted_label)
    if min_confidence is not None:
        clauses.append("results.confidence >= ?")
        params.append(min_confidence)
    if max_confidence is not None:
        clauses.append("results.confidence <= ?")
        params.append(max_confidence)
    if review_status:
        clauses.append("results.review_status = ?")
        params.append(review_status)

    sort_map = {
        "confidence": "results.confidence",
        "created_at": "results.created_at",
    }
    order_col = sort_map.get(sort_by, "results.confidence")
    direction = "DESC" if sort_dir.lower() == "desc" else "ASC"

    sql = f"""
        SELECT results.*,
               eval_cases.name AS case_name,
               eval_cases.prompt,
               eval_cases.response,
               eval_cases.expected_label,
               eval_cases.external_case_id,
               runs.project_id,
               runs.provider,
               runs.model
        FROM results
        JOIN eval_cases ON eval_cases.id = results.case_id
        JOIN runs ON runs.id = results.run_id
        WHERE {' AND '.join(clauses)}
        ORDER BY {order_col} {direction}, results.id ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    with get_conn() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def get_review_detail(result_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        result = _get_result(conn, result_id)
        if result is None:
            return None
        decisions = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM review_decisions
                WHERE result_id = ?
                ORDER BY created_at, id
                """,
                (result_id,),
            ).fetchall()
        )
    result["decisions"] = decisions
    return result


def _recompute_status(conn: Any, result_id: int) -> str:
    decisions = rows_to_dicts(
        conn.execute(
            "SELECT * FROM review_decisions WHERE result_id = ? ORDER BY id",
            (result_id,),
        ).fetchall()
    )
    if any(item["status"] == ReviewStatus.ADJUDICATED.value for item in decisions):
        status = ReviewStatus.ADJUDICATED.value
        final = next(
            item for item in decisions if item["status"] == ReviewStatus.ADJUDICATED.value
        )
        conn.execute(
            "UPDATE results SET review_status=?, final_label=? WHERE id=?",
            (status, final["final_label"], result_id),
        )
        return status

    labels = {item["final_label"] for item in decisions}
    if not decisions:
        status = ReviewStatus.PENDING.value
        conn.execute(
            "UPDATE results SET review_status=?, final_label=NULL WHERE id=?",
            (status, result_id),
        )
        return status
    if len(labels) > 1:
        status = ReviewStatus.DISAGREEMENT.value
        conn.execute(
            "UPDATE results SET review_status=?, final_label=NULL WHERE id=?",
            (status, result_id),
        )
        return status

    status = ReviewStatus.REVIEWED.value
    only_label = next(iter(labels))
    conn.execute(
        "UPDATE results SET review_status=?, final_label=? WHERE id=?",
        (status, only_label, result_id),
    )
    return status


def submit_decision(result_id: int, payload: ReviewDecisionCreate) -> dict[str, Any]:
    now = utc_now()
    with get_conn() as conn:
        result = _get_result(conn, result_id)
        if result is None:
            raise LookupError("Result not found")

        existing = conn.execute(
            "SELECT id FROM review_decisions WHERE result_id=? AND reviewer=?",
            (result_id, payload.reviewer),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE review_decisions
                SET final_label=?, comment=?, status=?, updated_at=?
                WHERE id=?
                """,
                (
                    payload.final_label,
                    payload.comment,
                    ReviewStatus.REVIEWED.value,
                    now,
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO review_decisions(
                    result_id, reviewer, final_label, comment, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    payload.reviewer,
                    payload.final_label,
                    payload.comment,
                    ReviewStatus.REVIEWED.value,
                    now,
                    now,
                ),
            )
        _recompute_status(conn, result_id)
    detail = get_review_detail(result_id)
    assert detail is not None
    return detail


def adjudicate(result_id: int, payload: AdjudicationCreate) -> dict[str, Any]:
    now = utc_now()
    with get_conn() as conn:
        result = _get_result(conn, result_id)
        if result is None:
            raise LookupError("Result not found")

        existing = conn.execute(
            "SELECT id FROM review_decisions WHERE result_id=? AND reviewer=?",
            (result_id, payload.adjudicator),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE review_decisions
                SET final_label=?, comment=?, status=?, updated_at=?
                WHERE id=?
                """,
                (
                    payload.final_label,
                    payload.comment,
                    ReviewStatus.ADJUDICATED.value,
                    now,
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO review_decisions(
                    result_id, reviewer, final_label, comment, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    payload.adjudicator,
                    payload.final_label,
                    payload.comment,
                    ReviewStatus.ADJUDICATED.value,
                    now,
                    now,
                ),
            )
        _recompute_status(conn, result_id)
    detail = get_review_detail(result_id)
    assert detail is not None
    return detail

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(os.getenv("EVAL_DB_PATH", "data/evals.db"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS eval_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        prompt TEXT NOT NULL,
        response TEXT NOT NULL,
        expected_label TEXT,
        requirements_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        external_case_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        metrics_json TEXT NOT NULL DEFAULT '{}',
        config_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        case_id INTEGER NOT NULL,
        verdict TEXT NOT NULL,
        severity TEXT NOT NULL,
        score REAL NOT NULL,
        confidence REAL NOT NULL,
        reason TEXT NOT NULL,
        evidence_json TEXT NOT NULL DEFAULT '[]',
        claims_json TEXT NOT NULL DEFAULT '[]',
        rule_findings_json TEXT NOT NULL DEFAULT '[]',
        needs_human_review INTEGER NOT NULL DEFAULT 0,
        review_status TEXT NOT NULL DEFAULT 'PENDING',
        final_label TEXT,
        raw_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
        FOREIGN KEY(case_id) REFERENCES eval_cases(id) ON DELETE CASCADE,
        UNIQUE(run_id, case_id)
    );

    CREATE TABLE IF NOT EXISTS review_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        result_id INTEGER NOT NULL,
        reviewer TEXT NOT NULL,
        final_label TEXT NOT NULL,
        comment TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(result_id) REFERENCES results(id) ON DELETE CASCADE,
        UNIQUE(result_id, reviewer)
    );
    """
    with get_conn() as conn:
        conn.executescript(schema)
        migrate_schema(conn)


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Non-destructive upgrades for existing SQLite databases."""
    _ensure_column(conn, "eval_cases", "external_case_id", "external_case_id TEXT")
    _ensure_column(conn, "runs", "config_json", "config_json TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(
        conn,
        "results",
        "review_status",
        "review_status TEXT NOT NULL DEFAULT 'PENDING'",
    )
    _ensure_column(conn, "results", "final_label", "final_label TEXT")

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
        CREATE INDEX IF NOT EXISTS idx_eval_cases_project_id ON eval_cases(project_id);
        CREATE INDEX IF NOT EXISTS idx_eval_cases_external_case_id
            ON eval_cases(project_id, external_case_id);
        CREATE INDEX IF NOT EXISTS idx_runs_project_id ON runs(project_id);
        CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
        CREATE INDEX IF NOT EXISTS idx_results_run_id ON results(run_id);
        CREATE INDEX IF NOT EXISTS idx_results_case_id ON results(case_id);
        CREATE INDEX IF NOT EXISTS idx_results_review_status ON results(review_status);
        CREATE INDEX IF NOT EXISTS idx_results_severity ON results(severity);
        CREATE INDEX IF NOT EXISTS idx_results_needs_human_review ON results(needs_human_review);
        CREATE INDEX IF NOT EXISTS idx_results_created_at ON results(created_at);
        CREATE INDEX IF NOT EXISTS idx_review_decisions_result_id ON review_decisions(result_id);
        CREATE INDEX IF NOT EXISTS idx_eval_cases_expected_label ON eval_cases(expected_label);
        """
    )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key in list(item):
        if key.endswith("_json"):
            try:
                item[key[:-5]] = json.loads(item.pop(key))
            except (TypeError, json.JSONDecodeError):
                item[key[:-5]] = None
    if "needs_human_review" in item:
        item["needs_human_review"] = bool(item["needs_human_review"])
    return item


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) or {} for row in rows]

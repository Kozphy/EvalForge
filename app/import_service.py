"""CSV / JSONL evaluation case import."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, BinaryIO

from pydantic import ValidationError

from .config import ALLOWED_IMPORT_EXTENSIONS, MAX_IMPORT_CASES, MAX_IMPORT_FILE_BYTES
from .db import get_conn, row_to_dict
from .schemas import EvalCaseCreate, ImportErrorItem, ImportResult, RequirementSpec

_UNSAFE_FILENAME = re.compile(r"[^\w.\- ]+", re.UNICODE)


def sanitize_filename(filename: str | None) -> str:
    raw = (filename or "upload").replace("\\", "/").split("/")[-1]
    cleaned = _UNSAFE_FILENAME.sub("_", raw).strip(". ")
    return cleaned[:180] or "upload"


def detect_import_format(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMPORT_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension {suffix!r}. Allowed: {', '.join(sorted(ALLOWED_IMPORT_EXTENSIONS))}."
        )
    return suffix.lstrip(".")


def _decode_upload(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8.") from exc


def _read_limited(file_obj: BinaryIO, max_bytes: int) -> bytes:
    chunk = file_obj.read(max_bytes + 1)
    if chunk is None:
        return b""
    if len(chunk) > max_bytes:
        raise ValueError(f"File exceeds maximum size of {max_bytes} bytes.")
    return chunk


def _error(row: int, code: str, message: str, field: str | None = None) -> ImportErrorItem:
    return ImportErrorItem(row=row, field=field, code=code, message=message)


def _parse_json_cell(value: str, *, field: str, row: int) -> tuple[Any | None, ImportErrorItem | None]:
    text = value.strip()
    if not text:
        return {} if field in {"requirements", "metadata"} else None, None
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, _error(row, "invalid_json_cell", f"Malformed JSON in {field}: {exc}", field)


def _validate_case_payload(payload: dict[str, Any], row: int) -> tuple[EvalCaseCreate | None, list[ImportErrorItem]]:
    errors: list[ImportErrorItem] = []
    try:
        case = EvalCaseCreate.model_validate(payload)
        # Force requirements validation early for clearer errors
        RequirementSpec.model_validate(case.requirements.model_dump())
        return case, errors
    except ValidationError as exc:
        for item in exc.errors():
            loc = ".".join(str(part) for part in item.get("loc", ())) or None
            msg = item.get("msg", "Validation failed")
            code = "invalid_label" if loc == "expected_label" else "validation_error"
            if "Field required" in msg or item.get("type") == "missing":
                code = "missing_field"
            errors.append(_error(row, code, msg, loc))
        return None, errors
    except ValueError as exc:
        errors.append(_error(row, "validation_error", str(exc)))
        return None, errors


def parse_jsonl_rows(text: str) -> tuple[list[tuple[int, EvalCaseCreate]], list[ImportErrorItem]]:
    cases: list[tuple[int, EvalCaseCreate]] = []
    errors: list[ImportErrorItem] = []
    lines = text.splitlines()
    if len(lines) > MAX_IMPORT_CASES:
        errors.append(
            _error(
                0,
                "too_many_rows",
                f"File contains more than {MAX_IMPORT_CASES} cases.",
            )
        )
        return [], errors

    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(_error(index, "malformed_jsonl", f"Malformed JSONL: {exc}"))
            continue
        if not isinstance(payload, dict):
            errors.append(_error(index, "invalid_row", "Each JSONL row must be an object."))
            continue
        case, row_errors = _validate_case_payload(payload, index)
        errors.extend(row_errors)
        if case is not None:
            cases.append((index, case))
    return cases, errors


def parse_csv_rows(text: str) -> tuple[list[tuple[int, EvalCaseCreate]], list[ImportErrorItem]]:
    cases: list[tuple[int, EvalCaseCreate]] = []
    errors: list[ImportErrorItem] = []
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], [_error(0, "missing_header", "CSV file is missing a header row.")]

    rows = list(reader)
    if len(rows) > MAX_IMPORT_CASES:
        return [], [
            _error(0, "too_many_rows", f"File contains more than {MAX_IMPORT_CASES} cases.")
        ]

    for index, row in enumerate(rows, start=2):  # header is row 1
        payload: dict[str, Any] = {}
        row_errors: list[ImportErrorItem] = []
        for key, value in row.items():
            if key is None:
                continue
            field = key.strip()
            cell = value if value is not None else ""
            if field in {"requirements", "metadata"}:
                parsed, err = _parse_json_cell(cell, field=field, row=index)
                if err:
                    row_errors.append(err)
                else:
                    payload[field] = parsed
            elif field == "expected_label":
                payload[field] = cell.strip() or None
            elif field == "case_id":
                payload[field] = cell.strip() or None
            else:
                payload[field] = cell

        if row_errors:
            errors.extend(row_errors)
            continue

        case, validation_errors = _validate_case_payload(payload, index)
        errors.extend(validation_errors)
        if case is not None:
            cases.append((index, case))
    return cases, errors


def _existing_external_ids(project_id: int) -> set[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT external_case_id FROM eval_cases
            WHERE project_id = ? AND external_case_id IS NOT NULL
            """,
            (project_id,),
        ).fetchall()
    return {str(row["external_case_id"]) for row in rows if row["external_case_id"]}


def _insert_case(conn: Any, project_id: int, case: EvalCaseCreate) -> None:
    expected = case.expected_label
    conn.execute(
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
            expected,
            case.requirements.model_dump_json(),
            json.dumps(case.metadata, ensure_ascii=False),
            case.case_id,
        ),
    )


def import_cases_from_upload(
    project_id: int,
    *,
    filename: str,
    file_obj: BinaryIO,
    dry_run: bool = False,
    atomic: bool = True,
    max_bytes: int | None = None,
) -> ImportResult:
    with get_conn() as conn:
        project = row_to_dict(conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
    if project is None:
        raise LookupError("Project not found")

    limit = MAX_IMPORT_FILE_BYTES if max_bytes is None else max_bytes
    safe_name = sanitize_filename(filename)
    fmt = detect_import_format(safe_name)
    raw = _read_limited(file_obj, limit)
    text = _decode_upload(raw)

    if fmt == "jsonl":
        cases, errors = parse_jsonl_rows(text)
    else:
        cases, errors = parse_csv_rows(text)

    existing = _existing_external_ids(project_id)
    seen_in_file: set[str] = set()
    accepted: list[tuple[int, EvalCaseCreate]] = []
    duplicate_rows = 0

    for row_num, case in cases:
        external_id = case.case_id
        if external_id:
            if external_id in existing or external_id in seen_in_file:
                duplicate_rows += 1
                errors.append(
                    _error(
                        row_num,
                        "duplicate_case_id",
                        f"Duplicate case_id {external_id!r}.",
                        "case_id",
                    )
                )
                continue
            seen_in_file.add(external_id)
        accepted.append((row_num, case))

    validated_rows = len(accepted)
    rejected_rows = len(errors)
    # Count only row-level validation/dup errors for rejected; structural errors may have row=0
    imported_rows = 0

    if dry_run:
        return ImportResult(
            filename=safe_name,
            dry_run=True,
            atomic=atomic,
            total_rows=validated_rows + duplicate_rows + sum(1 for e in errors if e.code != "duplicate_case_id"),
            validated_rows=validated_rows,
            imported_rows=0,
            rejected_rows=rejected_rows,
            duplicate_rows=duplicate_rows,
            errors=errors,
        )

    # Recompute total_rows more accurately from parsed content
    total_rows = validated_rows + sum(
        1 for e in errors if e.code in {"malformed_jsonl", "invalid_row", "validation_error", "invalid_label", "missing_field", "invalid_json_cell", "duplicate_case_id"}
    )

    if atomic and errors:
        return ImportResult(
            filename=safe_name,
            dry_run=False,
            atomic=True,
            total_rows=max(total_rows, validated_rows + rejected_rows),
            validated_rows=validated_rows,
            imported_rows=0,
            rejected_rows=rejected_rows,
            duplicate_rows=duplicate_rows,
            errors=errors,
        )

    with get_conn() as conn:
        for _, case in accepted:
            _insert_case(conn, project_id, case)
            imported_rows += 1

    return ImportResult(
        filename=safe_name,
        dry_run=False,
        atomic=atomic,
        total_rows=max(total_rows, imported_rows + rejected_rows),
        validated_rows=validated_rows,
        imported_rows=imported_rows,
        rejected_rows=rejected_rows,
        duplicate_rows=duplicate_rows,
        errors=errors,
    )

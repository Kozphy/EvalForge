from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.graders import calculate_metrics, check_rules, heuristic_grade, split_sentences, validate_sql_syntax
from app.schemas import RequirementSpec


def test_split_sentences_handles_english_and_chinese() -> None:
    assert split_sentences("One. Two!") == ["One.", "Two!"]
    assert split_sentences("第一句。第二句！") == ["第一句。", "第二句！"]


def test_rule_checks_find_core_format_failure() -> None:
    requirements = RequirementSpec(exact_sentences=2, required_phrases=["Jamie"])
    findings = check_rules("Jamie, I cannot attend.", requirements)
    assert any(item.rule_type == "exact_sentences" and not item.passed for item in findings)
    assert any(item.rule_type == "required_phrase" and item.passed for item in findings)


def test_heuristic_routes_missing_evidence_to_review() -> None:
    output, rules = heuristic_grade(
        "Explain a scientific claim.",
        "A newly invented planet has twelve purple moons.",
        RequirementSpec(),
        evidence=[],
    )
    assert rules == []
    assert output.needs_human_review is True
    assert output.severity == "minor"
    assert output.claims[0].verdict == "unsupported"


def test_major_instruction_failure() -> None:
    output, _ = heuristic_grade(
        "Answer with one word.",
        "This answer uses several words.",
        RequirementSpec(max_words=1),
        evidence=[],
    )
    assert output.severity in {"minor", "major"}


def test_metrics() -> None:
    metrics = calculate_metrics(
        ["no_issue", "major", "minor"],
        ["no_issue", "minor", "minor"],
    )
    assert metrics["accuracy"] == 0.6667
    assert metrics["confusion_matrix"]["major"]["minor"] == 1


def _by_type(findings, rule_type: str):
    return [item for item in findings if item.rule_type == rule_type]


def test_min_max_words_and_sentences() -> None:
    text = "One sentence only."
    findings = check_rules(
        text,
        RequirementSpec(min_words=2, max_words=10, min_sentences=1, max_sentences=1, exact_sentences=1),
    )
    assert all(item.passed for item in findings)

    empty = check_rules("", RequirementSpec(min_words=1, min_sentences=1))
    assert any(not item.passed for item in empty)


def test_unicode_and_multiline() -> None:
    text = "第一句包含 Jamie。\n第二句继续。"
    findings = check_rules(
        text,
        RequirementSpec(exact_sentences=2, required_phrases=["Jamie"], forbidden_phrases=["禁止"]),
    )
    assert _by_type(findings, "exact_sentences")[0].passed
    assert _by_type(findings, "required_phrase")[0].passed


def test_regex_rules_and_invalid_config() -> None:
    findings = check_rules(
        "Invoice total is 12.50",
        RequirementSpec(required_regex=[r"\d+\.\d{2}"], forbidden_regex=[r"TODO"]),
    )
    assert _by_type(findings, "required_regex")[0].passed
    assert _by_type(findings, "forbidden_regex")[0].passed

    with pytest.raises(ValidationError):
        RequirementSpec(required_regex=["[unterminated"])


def test_json_schema_and_keys() -> None:
    schema = {
        "type": "object",
        "properties": {"total": {"type": "number"}},
        "required": ["total"],
    }
    ok = check_rules('{"total": 10}', RequirementSpec(require_json=True, json_schema=schema, required_json_keys=["total"]))
    assert all(item.passed for item in ok if item.rule_type in {"valid_json", "json_schema", "required_json_keys"})

    bad = check_rules('{"amount": 10}', RequirementSpec(json_schema=schema, forbidden_json_keys=["amount"]))
    assert any(item.rule_type == "json_schema" and not item.passed for item in bad)
    assert any(item.rule_type == "forbidden_json_keys" and not item.passed for item in bad)

    malformed = check_rules("{", RequirementSpec(require_json=True))
    assert any(item.rule_type == "valid_json" and not item.passed for item in malformed)


def test_exact_normalized_match_and_formats() -> None:
    assert _by_type(
        check_rules("  Hello   World ", RequirementSpec(exact_normalized_match="hello world")),
        "exact_normalized_match",
    )[0].passed
    assert _by_type(check_rules("2024-01-02", RequirementSpec(require_date_format=True)), "date_format")[0].passed
    assert _by_type(check_rules("a@b.com", RequirementSpec(require_email_format=True)), "email_format")[0].passed
    assert _by_type(
        check_rules("https://example.com/x", RequirementSpec(require_url_format=True)),
        "url_format",
    )[0].passed


def test_citations_python_sql() -> None:
    cite = check_rules("See [doc-1] and (IAS 16).", RequirementSpec(require_citation=True, citation_ids=["doc-1"]))
    assert _by_type(cite, "citation_presence")[0].passed
    assert _by_type(cite, "citation_ids")[0].passed

    py_ok = check_rules("x = 1\nprint(x)", RequirementSpec(require_python_syntax=True))
    assert _by_type(py_ok, "python_syntax")[0].passed
    py_bad = check_rules("def (", RequirementSpec(require_python_syntax=True))
    assert not _by_type(py_bad, "python_syntax")[0].passed

    sql_ok, _ = validate_sql_syntax("SELECT id FROM invoices WHERE total > 0")
    assert sql_ok
    sql_findings = check_rules("SELECT * FROM t", RequirementSpec(require_sql_syntax=True))
    assert _by_type(sql_findings, "sql_syntax")[0].passed
    sql_bad = check_rules("ATTACH DATABASE 'x'", RequirementSpec(require_sql_syntax=True))
    assert not _by_type(sql_bad, "sql_syntax")[0].passed


def test_structured_finding_schema() -> None:
    findings = check_rules("{}", RequirementSpec(require_json=True, json_schema={"type": "object", "required": ["total"]}))
    item = _by_type(findings, "json_schema")[0]
    assert item.passed is False
    assert item.expected
    assert item.observed
    assert item.message

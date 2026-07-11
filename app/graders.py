from __future__ import annotations

import ast
import json
import os
import re
from collections import Counter
from typing import Any, Iterable
from urllib.parse import urlparse

import jsonschema

from .schemas import (
    ClaimAssessment,
    GraderOutput,
    RequirementSpec,
    RuleFinding,
    Severity,
)

_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}$|"
    r"^\d{1,2}/\d{1,2}/\d{2,4}$|"
    r"^\d{1,2}-\d{1,2}-\d{2,4}$"
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CITATION_RE = re.compile(r"\[([^\]]+)\]|\(([^)]+)\)")

# Conservative SQL keyword / structure checks — does not execute SQL.
_SQL_FORBIDDEN = re.compile(
    r"\b(ATTACH|DETACH|PRAGMA|LOAD_EXTENSION|INTO\s+OUTFILE)\b",
    re.IGNORECASE,
)
_SQL_START = re.compile(
    r"^\s*(SELECT|WITH|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|EXPLAIN)\b",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s*", text.strip())
    return [part.strip() for part in parts if part.strip()]


def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _finding(
    rule_type: str,
    *,
    passed: bool,
    severity: Severity,
    message: str,
    expected: str | None = None,
    observed: str | None = None,
) -> RuleFinding:
    return RuleFinding(
        rule_type=rule_type,
        rule=rule_type,
        passed=passed,
        severity=severity,
        expected=expected,
        observed=observed,
        message=message,
        detail=message,
    )


def _parse_json(response: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(response), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def validate_sql_syntax(sql: str) -> tuple[bool, str]:
    """Conservative SQL syntax check without execution.

    Limitations: does not fully parse SQL dialects; rejects empty input,
    dangerous keywords, and statements that do not start with a known verb.
    """
    cleaned = sql.strip()
    if not cleaned:
        return False, "SQL text is empty."
    if _SQL_FORBIDDEN.search(cleaned):
        return False, "SQL contains disallowed keywords for offline validation."
    if not _SQL_START.match(cleaned):
        return False, "SQL must start with a recognized statement keyword."
    # Basic balance checks for parentheses and quotes
    if cleaned.count("(") != cleaned.count(")"):
        return False, "Unbalanced parentheses in SQL."
    single = cleaned.count("'") - cleaned.count("''") * 2
    if single % 2 != 0:
        return False, "Unbalanced single quotes in SQL."
    return True, "SQL passed conservative syntax checks."


def check_rules(response: str, requirements: RequirementSpec) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    sentences = split_sentences(response)
    words = count_words(response)
    lower = response.casefold()

    if requirements.exact_sentences is not None:
        passed = len(sentences) == requirements.exact_sentences
        findings.append(
            _finding(
                "exact_sentences",
                passed=passed,
                severity="no_issue" if passed else "major",
                expected=str(requirements.exact_sentences),
                observed=str(len(sentences)),
                message=f"Expected {requirements.exact_sentences}; observed {len(sentences)}.",
            )
        )

    if requirements.min_sentences is not None:
        passed = len(sentences) >= requirements.min_sentences
        findings.append(
            _finding(
                "min_sentences",
                passed=passed,
                severity="no_issue" if passed else "minor",
                expected=str(requirements.min_sentences),
                observed=str(len(sentences)),
                message=f"Minimum {requirements.min_sentences}; observed {len(sentences)}.",
            )
        )

    if requirements.max_sentences is not None:
        passed = len(sentences) <= requirements.max_sentences
        findings.append(
            _finding(
                "max_sentences",
                passed=passed,
                severity="no_issue" if passed else "minor",
                expected=str(requirements.max_sentences),
                observed=str(len(sentences)),
                message=f"Maximum {requirements.max_sentences}; observed {len(sentences)}.",
            )
        )

    if requirements.min_words is not None:
        passed = words >= requirements.min_words
        findings.append(
            _finding(
                "min_words",
                passed=passed,
                severity="no_issue" if passed else "minor",
                expected=str(requirements.min_words),
                observed=str(words),
                message=f"Minimum {requirements.min_words}; observed {words}.",
            )
        )

    if requirements.max_words is not None:
        passed = words <= requirements.max_words
        findings.append(
            _finding(
                "max_words",
                passed=passed,
                severity="no_issue" if passed else "major",
                expected=str(requirements.max_words),
                observed=str(words),
                message=f"Maximum {requirements.max_words}; observed {words}.",
            )
        )

    for phrase in requirements.required_phrases:
        passed = phrase.casefold() in lower
        findings.append(
            _finding(
                "required_phrase",
                passed=passed,
                severity="no_issue" if passed else "major",
                expected=phrase,
                observed="present" if passed else "missing",
                message="Required phrase found." if passed else "Required phrase missing.",
            )
        )

    for phrase in requirements.forbidden_phrases:
        passed = phrase.casefold() not in lower
        findings.append(
            _finding(
                "forbidden_phrase",
                passed=passed,
                severity="no_issue" if passed else "major",
                expected=f"absent:{phrase}",
                observed="absent" if passed else "present",
                message="Forbidden phrase absent." if passed else "Forbidden phrase present.",
            )
        )

    for pattern in requirements.required_regex:
        matched = re.search(pattern, response, flags=re.MULTILINE) is not None
        findings.append(
            _finding(
                "required_regex",
                passed=matched,
                severity="no_issue" if matched else "major",
                expected=pattern,
                observed="matched" if matched else "not_matched",
                message="Required regex matched." if matched else "Required regex did not match.",
            )
        )

    for pattern in requirements.forbidden_regex:
        matched = re.search(pattern, response, flags=re.MULTILINE) is not None
        findings.append(
            _finding(
                "forbidden_regex",
                passed=not matched,
                severity="no_issue" if not matched else "major",
                expected=f"no_match:{pattern}",
                observed="matched" if matched else "not_matched",
                message="Forbidden regex absent." if not matched else "Forbidden regex matched.",
            )
        )

    parsed: Any | None = None
    parse_error: str | None = None
    needs_json = (
        requirements.require_json
        or requirements.json_schema is not None
        or bool(requirements.required_json_keys)
        or bool(requirements.forbidden_json_keys)
    )
    if needs_json:
        parsed, parse_error = _parse_json(response)
        passed = parsed is not None
        findings.append(
            _finding(
                "valid_json",
                passed=passed,
                severity="no_issue" if passed else "major",
                expected="valid JSON",
                observed=parse_error or "valid JSON",
                message="Response is valid JSON." if passed else "Response is not valid JSON.",
            )
        )

    if requirements.json_schema is not None:
        if parsed is None:
            findings.append(
                _finding(
                    "json_schema",
                    passed=False,
                    severity="major",
                    expected="schema-valid JSON",
                    observed=parse_error or "not JSON",
                    message="Cannot validate JSON Schema because the response is not valid JSON.",
                )
            )
        else:
            try:
                jsonschema.validate(instance=parsed, schema=requirements.json_schema)
                findings.append(
                    _finding(
                        "json_schema",
                        passed=True,
                        severity="no_issue",
                        expected="schema match",
                        observed="matched",
                        message="The response matches the configured JSON Schema.",
                    )
                )
            except Exception as exc:  # jsonschema.ValidationError or SchemaError
                findings.append(
                    _finding(
                        "json_schema",
                        passed=False,
                        severity="major",
                        expected="schema match",
                        observed=str(exc),
                        message="The response is valid JSON but does not match the configured schema.",
                    )
                )

    if requirements.required_json_keys:
        if not isinstance(parsed, dict):
            findings.append(
                _finding(
                    "required_json_keys",
                    passed=False,
                    severity="major",
                    expected=",".join(requirements.required_json_keys),
                    observed="not an object",
                    message="Required JSON keys cannot be checked because the response is not a JSON object.",
                )
            )
        else:
            missing = [key for key in requirements.required_json_keys if key not in parsed]
            findings.append(
                _finding(
                    "required_json_keys",
                    passed=not missing,
                    severity="no_issue" if not missing else "major",
                    expected=",".join(requirements.required_json_keys),
                    observed="all present" if not missing else f"missing:{','.join(missing)}",
                    message="All required JSON keys present."
                    if not missing
                    else f"Missing required JSON keys: {', '.join(missing)}.",
                )
            )

    if requirements.forbidden_json_keys:
        if not isinstance(parsed, dict):
            findings.append(
                _finding(
                    "forbidden_json_keys",
                    passed=False,
                    severity="major",
                    expected="JSON object without forbidden keys",
                    observed="not an object",
                    message="Forbidden JSON keys cannot be checked because the response is not a JSON object.",
                )
            )
        else:
            present = [key for key in requirements.forbidden_json_keys if key in parsed]
            findings.append(
                _finding(
                    "forbidden_json_keys",
                    passed=not present,
                    severity="no_issue" if not present else "major",
                    expected="absent",
                    observed="absent" if not present else f"present:{','.join(present)}",
                    message="No forbidden JSON keys present."
                    if not present
                    else f"Forbidden JSON keys present: {', '.join(present)}.",
                )
            )

    if requirements.exact_normalized_match is not None:
        passed = normalize_text(response) == normalize_text(requirements.exact_normalized_match)
        findings.append(
            _finding(
                "exact_normalized_match",
                passed=passed,
                severity="no_issue" if passed else "major",
                expected=normalize_text(requirements.exact_normalized_match),
                observed=normalize_text(response),
                message="Normalized text matches." if passed else "Normalized text does not match.",
            )
        )

    if requirements.require_date_format:
        candidate = response.strip()
        passed = bool(_DATE_RE.match(candidate))
        findings.append(
            _finding(
                "date_format",
                passed=passed,
                severity="no_issue" if passed else "minor",
                expected="YYYY-MM-DD or common slash/dash date",
                observed=candidate[:80],
                message="Response matches a supported date format."
                if passed
                else "Response is not a supported date format.",
            )
        )

    if requirements.require_email_format:
        candidate = response.strip()
        passed = bool(_EMAIL_RE.match(candidate))
        findings.append(
            _finding(
                "email_format",
                passed=passed,
                severity="no_issue" if passed else "minor",
                expected="user@domain.tld",
                observed=candidate[:80],
                message="Response looks like an email address."
                if passed
                else "Response is not a valid email format.",
            )
        )

    if requirements.require_url_format:
        candidate = response.strip()
        parsed_url = urlparse(candidate)
        passed = parsed_url.scheme in {"http", "https"} and bool(parsed_url.netloc)
        findings.append(
            _finding(
                "url_format",
                passed=passed,
                severity="no_issue" if passed else "minor",
                expected="http(s) URL",
                observed=candidate[:120],
                message="Response looks like a URL." if passed else "Response is not a valid URL.",
            )
        )

    if requirements.require_citation or requirements.citation_ids:
        found_ids = {
            (m.group(1) or m.group(2) or "").strip()
            for m in _CITATION_RE.finditer(response)
            if (m.group(1) or m.group(2) or "").strip()
        }
        if requirements.require_citation:
            passed = bool(found_ids)
            findings.append(
                _finding(
                    "citation_presence",
                    passed=passed,
                    severity="no_issue" if passed else "minor",
                    expected="at least one citation",
                    observed=",".join(sorted(found_ids)) or "none",
                    message="Citation markers found." if passed else "No citation markers found.",
                )
            )
        if requirements.citation_ids:
            missing = [cid for cid in requirements.citation_ids if cid not in found_ids]
            findings.append(
                _finding(
                    "citation_ids",
                    passed=not missing,
                    severity="no_issue" if not missing else "major",
                    expected=",".join(requirements.citation_ids),
                    observed=",".join(sorted(found_ids)) or "none",
                    message="All required citation IDs present."
                    if not missing
                    else f"Missing citation IDs: {', '.join(missing)}.",
                )
            )

    if requirements.require_python_syntax:
        try:
            ast.parse(response)
            findings.append(
                _finding(
                    "python_syntax",
                    passed=True,
                    severity="no_issue",
                    expected="parseable Python",
                    observed="ok",
                    message="Response parses as Python via ast.parse.",
                )
            )
        except SyntaxError as exc:
            findings.append(
                _finding(
                    "python_syntax",
                    passed=False,
                    severity="major",
                    expected="parseable Python",
                    observed=str(exc),
                    message="Response is not valid Python syntax.",
                )
            )

    if requirements.require_sql_syntax:
        passed, detail = validate_sql_syntax(response)
        findings.append(
            _finding(
                "sql_syntax",
                passed=passed,
                severity="no_issue" if passed else "major",
                expected="conservative SQL syntax",
                observed=detail,
                message=detail,
            )
        )

    return findings


def extract_claims_heuristic(response: str) -> list[str]:
    claims = []
    for sentence in split_sentences(response):
        cleaned = sentence.strip(" -•\t")
        if len(cleaned.split()) >= 4 or len(cleaned) >= 16:
            claims.append(cleaned)
    return claims[:12]


def _token_set(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[\w'-]+", text, flags=re.UNICODE)
        if len(token) > 2
    }


def _overlap(claim: str, evidence: str) -> float:
    a = _token_set(claim)
    b = _token_set(evidence)
    if not a:
        return 0.0
    return len(a & b) / len(a)


def _has_negation(text: str) -> bool:
    english_negations = {"not", "never", "no", "without", "isn't", "aren't", "doesn't", "don't"}
    tokens = {token.casefold() for token in re.findall(r"[\w']+", text, flags=re.UNICODE)}
    chinese_negations = ("不是", "不會", "沒有", "並非", "不得", "無法", "不應", "不需")
    return bool(tokens & english_negations) or any(term in text for term in chinese_negations)


def _negation_mismatch(claim: str, evidence: str) -> bool:
    return _has_negation(claim) != _has_negation(evidence)


def _best_evidence_sentence(claim: str, evidence: list[dict]) -> tuple[float, dict | None, str]:
    best_score = 0.0
    best_item: dict | None = None
    best_sentence = ""
    for item in evidence:
        sentences = split_sentences(item["text"]) or [item["text"]]
        for sentence in sentences:
            score = _overlap(claim, sentence)
            if score > best_score:
                best_score = score
                best_item = item
                best_sentence = sentence
    return best_score, best_item, best_sentence


def heuristic_grade(
    prompt: str,
    response: str,
    requirements: RequirementSpec,
    evidence: list[dict],
) -> tuple[GraderOutput, list[RuleFinding]]:
    del prompt  # Kept in the signature so providers are interchangeable.
    rules = check_rules(response, requirements)
    claims = extract_claims_heuristic(response)
    assessments: list[ClaimAssessment] = []

    for claim in claims:
        best_score, best, best_sentence = _best_evidence_sentence(claim, evidence)

        if best is None or best_score < 0.12:
            verdict = "unsupported"
            confidence = 0.55
            ids: list[str] = []
            reason = "No sufficiently similar local evidence sentence was retrieved."
        elif best_score >= 0.28 and _negation_mismatch(claim, best_sentence):
            verdict = "contradicted"
            confidence = min(0.92, 0.55 + best_score / 2)
            ids = [best["chunk_id"]]
            reason = "The closest evidence sentence has substantial overlap but an opposing negation."
        elif best_score >= 0.28:
            verdict = "supported"
            confidence = min(0.92, 0.55 + best_score / 2)
            ids = [best["chunk_id"]]
            reason = "The claim substantially overlaps with a retrieved local evidence sentence."
        else:
            verdict = "uncertain"
            confidence = 0.5
            ids = [best["chunk_id"]]
            reason = "The retrieved evidence is related but not strong enough for a reliable verdict."

        assessments.append(
            ClaimAssessment(
                claim=claim,
                verdict=verdict,
                confidence=confidence,
                evidence_chunk_ids=ids,
                reason=reason,
            )
        )

    failed_rules = [item for item in rules if not item.passed]
    claim_counts = Counter(item.verdict for item in assessments)

    if any(item.severity == "major" for item in failed_rules) or claim_counts["contradicted"]:
        severity = "major"
        verdict = "fail"
        score = 0.0
    elif failed_rules or claim_counts["unsupported"] or claim_counts["uncertain"]:
        severity = "minor"
        verdict = "review"
        score = 0.5
    else:
        severity = "no_issue"
        verdict = "pass"
        score = 1.0

    needs_review = bool(claim_counts["unsupported"] or claim_counts["uncertain"])
    reason_bits = []
    if failed_rules:
        reason_bits.append(f"{len(failed_rules)} instruction/rule check(s) failed")
    if assessments:
        reason_bits.append(
            ", ".join(f"{name}={count}" for name, count in sorted(claim_counts.items()))
        )
    if not reason_bits:
        reason_bits.append("All configured checks passed")

    output = GraderOutput(
        verdict=verdict,
        severity=severity,
        score=score,
        confidence=0.65 if needs_review else 0.8,
        reason="; ".join(reason_bits) + ".",
        claims=assessments,
        needs_human_review=needs_review,
    )
    return output, rules


def openai_grade(
    prompt: str,
    response: str,
    requirements: RequirementSpec,
    evidence: list[dict],
    model: str,
) -> tuple[GraderOutput, list[RuleFinding]]:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - dependency is included in requirements
        raise RuntimeError("The openai package is not installed.") from exc

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for the OpenAI provider.")

    rules = check_rules(response, requirements)
    evidence_text = "\n\n".join(
        f"[{item['chunk_id']}] {item['title']}\n{item['text']}" for item in evidence
    ) or "No local evidence was retrieved."
    rule_text = "\n".join(
        f"- {item.rule_type}: {'PASS' if item.passed else 'FAIL'} ({item.message})" for item in rules
    ) or "No deterministic requirements were configured."

    instructions = """
You are a conservative AI evaluation grader. Evaluate only against the supplied prompt,
response, deterministic rule results, and local evidence. Do not treat your own memory as
evidence. Separate contradicted from unsupported. Mark needs_human_review when evidence is
missing, ambiguous, conflicting, or high-risk. Severity meanings: no_issue = fully usable;
minor = localized issue that does not overturn the main answer; major = central factual error
or failure of a core explicit instruction. Return the supplied structured schema.
""".strip()
    input_text = f"""
USER PROMPT:
{prompt}

CANDIDATE RESPONSE:
{response}

REQUIREMENTS:
{requirements.model_dump_json(indent=2)}

DETERMINISTIC RULE RESULTS:
{rule_text}

LOCAL EVIDENCE:
{evidence_text}
""".strip()

    client = OpenAI()
    parsed = client.responses.parse(
        model=model,
        instructions=instructions,
        input=input_text,
        text_format=GraderOutput,
        store=False,
    )
    if parsed.output_parsed is None:
        raise RuntimeError("The grader returned no parsed structured output.")
    return parsed.output_parsed, rules


def calculate_metrics(expected: Iterable[str | None], predicted: Iterable[str]) -> dict:
    pairs = [(e, p) for e, p in zip(expected, predicted) if e is not None]
    labels = ["no_issue", "minor", "major"]
    matrix = {actual: {pred: 0 for pred in labels} for actual in labels}
    for actual, pred in pairs:
        if actual in matrix and pred in matrix[actual]:
            matrix[actual][pred] += 1

    total = len(pairs)
    correct = sum(1 for actual, pred in pairs if actual == pred)
    per_label = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[actual][label] for actual in labels if actual != label)
        fn = sum(matrix[label][pred] for pred in labels if pred != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(matrix[label].values()),
        }

    return {
        "labeled_cases": total,
        "accuracy": round(correct / total, 4) if total else None,
        "confusion_matrix": matrix,
        "per_label": per_label,
    }

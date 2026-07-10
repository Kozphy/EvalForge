from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Iterable

from .schemas import (
    ClaimAssessment,
    GraderOutput,
    RequirementSpec,
    RuleFinding,
)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s*", text.strip())
    return [part.strip() for part in parts if part.strip()]


def check_rules(response: str, requirements: RequirementSpec) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    sentences = split_sentences(response)
    words = re.findall(r"\b\w+\b", response, flags=re.UNICODE)

    if requirements.exact_sentences is not None:
        passed = len(sentences) == requirements.exact_sentences
        findings.append(
            RuleFinding(
                rule="exact_sentences",
                passed=passed,
                severity="no_issue" if passed else "major",
                detail=f"Expected {requirements.exact_sentences}; observed {len(sentences)}.",
            )
        )

    if requirements.max_sentences is not None:
        passed = len(sentences) <= requirements.max_sentences
        findings.append(
            RuleFinding(
                rule="max_sentences",
                passed=passed,
                severity="no_issue" if passed else "minor",
                detail=f"Maximum {requirements.max_sentences}; observed {len(sentences)}.",
            )
        )

    if requirements.max_words is not None:
        passed = len(words) <= requirements.max_words
        findings.append(
            RuleFinding(
                rule="max_words",
                passed=passed,
                severity="no_issue" if passed else "major",
                detail=f"Maximum {requirements.max_words}; observed {len(words)}.",
            )
        )

    lower = response.casefold()
    for phrase in requirements.required_phrases:
        passed = phrase.casefold() in lower
        findings.append(
            RuleFinding(
                rule=f"required_phrase:{phrase}",
                passed=passed,
                severity="no_issue" if passed else "major",
                detail="Required phrase found." if passed else "Required phrase missing.",
            )
        )

    for phrase in requirements.forbidden_phrases:
        passed = phrase.casefold() not in lower
        findings.append(
            RuleFinding(
                rule=f"forbidden_phrase:{phrase}",
                passed=passed,
                severity="no_issue" if passed else "major",
                detail="Forbidden phrase absent." if passed else "Forbidden phrase present.",
            )
        )

    if requirements.require_json:
        try:
            json.loads(response)
            passed = True
        except json.JSONDecodeError:
            passed = False
        findings.append(
            RuleFinding(
                rule="valid_json",
                passed=passed,
                severity="no_issue" if passed else "major",
                detail="Response is valid JSON." if passed else "Response is not valid JSON.",
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
        f"- {item.rule}: {'PASS' if item.passed else 'FAIL'} ({item.detail})" for item in rules
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

"""Evaluator systems compared in the RQ1/RQ2 experiment.

All systems are compositions of existing EvalForge components:

* deterministic rules     -> ``app.graders.check_rules``
* evidence retrieval      -> ``app.retrieval.retrieve`` (TF-IDF) + cited-document resolution
* structured judge        -> ``research.judge`` (LLM, offline stand-in, or replay)
* uncertainty + routing   -> ``app.controls.evaluate_controls``

Decision rule (fixed before any test-split result was produced):

1. Any failed deterministic rule => ``fail`` (final, never overridden by the judge).
2. Any cited knowledge-base ID that does not exist in the approved corpus => ``fail``
   (category ``hallucination``; part of the retrieval/grounding component).
3. Otherwise the judge verdict decides; a controls ``block`` (e.g. contradicted claim) => ``fail``.
4. If routing is enabled and the decision rests on the judge, the case is routed to human
   review when controls return ``review`` or the judge output is unusable. Routing does not
   change the automated label; it is evaluated separately (see METRICS.md).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Literal

from app.controls import ControlPolicy, evaluate_controls
from app.graders import check_rules, heuristic_grade
from app.retrieval import retrieve
from app.schemas import ClaimAssessment, GraderOutput, RuleFinding
from research.dataset import BenchmarkCase, CorpusDocument
from research.judge import Judge, JudgeCall, JudgeRequest

JudgeMode = Literal["none", "judge", "heuristic_grader"]

_KB_CITATION_RE = re.compile(r"\[(KB-\d+)\]")

RULE_CATEGORY = {
    "exact_sentences": "format_error",
    "min_sentences": "format_error",
    "max_sentences": "format_error",
    "min_words": "format_error",
    "max_words": "format_error",
    "valid_json": "format_error",
    "json_schema": "format_error",
    "required_json_keys": "format_error",
    "forbidden_json_keys": "format_error",
    "required_phrase": "missing_required_information",
    "required_regex": "missing_required_information",
    "forbidden_phrase": "instruction_violation",
    "forbidden_regex": "instruction_violation",
    "citation_presence": "instruction_violation",
    "citation_ids": "instruction_violation",
}


@dataclass(frozen=True)
class SystemSpec:
    name: str
    label: str
    use_rules: bool
    use_retrieval: bool
    judge_mode: JudgeMode
    use_routing: bool
    description: str


SYSTEMS: dict[str, SystemSpec] = {
    spec.name: spec
    for spec in (
        SystemSpec("B1_deterministic", "Deterministic-only", True, False, "none", False,
                   "Rule checks only; any failed rule => fail, otherwise pass."),
        SystemSpec("B2_single_judge", "Single judge", False, False, "judge", False,
                   "One judge call, no retrieved evidence, no rules, no routing."),
        SystemSpec("B3_grounded_judge", "Grounded judge", False, True, "judge", False,
                   "Approved-evidence retrieval, then one judge call; no rules, no routing."),
        SystemSpec("B4_hybrid", "EvalForge hybrid", True, True, "judge", True,
                   "Rules -> retrieval -> structured judge -> controls/uncertainty -> routing."),
        SystemSpec("A1_minus_rules", "Hybrid - rules", False, True, "judge", True,
                   "B4 without deterministic rules."),
        SystemSpec("A2_minus_retrieval", "Hybrid - retrieval", True, False, "judge", True,
                   "B4 without retrieval or citation resolution; judge sees no evidence."),
        SystemSpec("A3_minus_judge", "Hybrid - judge", True, True, "heuristic_grader", True,
                   "B4 with the judge replaced by EvalForge's lexical claim grader."),
        SystemSpec("A4_minus_routing", "Hybrid - routing", True, True, "judge", False,
                   "B4 without human-review routing."),
    )
}

PRIMARY_SYSTEMS = ("B1_deterministic", "B2_single_judge", "B3_grounded_judge", "B4_hybrid")
ABLATIONS = ("A1_minus_rules", "A2_minus_retrieval", "A3_minus_judge", "A4_minus_routing")


@dataclass(frozen=True)
class RetrievalConfig:
    backend: str = "tfidf"
    top_k: int = 4
    include_cited_documents: bool = True


def kb_numeric_id(doc_id: str) -> int:
    return int(doc_id.split("-")[1])


def cited_ids(response: str) -> list[str]:
    seen: list[str] = []
    for match in _KB_CITATION_RE.finditer(response):
        if match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def gather_evidence(case: BenchmarkCase, corpus: list[CorpusDocument], config: RetrievalConfig) -> list[dict]:
    """Document-level evidence: top-k retrieved chunks merged per document, plus cited documents."""
    by_id = {doc.doc_id: doc for doc in corpus}
    documents = [{"id": kb_numeric_id(d.doc_id), "title": d.title, "content": d.content} for d in corpus]
    query = f"{case.prompt}\n{case.candidate_response}"
    hits = retrieve(query, documents, top_k=config.top_k, backend=config.backend)

    merged: dict[str, dict] = {}
    for hit in hits:
        doc_id = f"KB-{hit['document_id']:02d}"
        entry = merged.setdefault(
            doc_id,
            {"doc_id": doc_id, "title": hit["title"], "text": by_id[doc_id].content, "score": 0.0,
             "via": "retrieval", "chunk_ids": []},
        )
        entry["score"] = max(entry["score"], round(float(hit["score"]), 6))
        entry["chunk_ids"].append(hit["chunk_id"])
    if config.include_cited_documents:
        for doc_id in cited_ids(case.candidate_response):
            if doc_id in by_id and doc_id not in merged:
                doc = by_id[doc_id]
                merged[doc_id] = {"doc_id": doc_id, "title": doc.title, "text": doc.content, "score": None,
                                  "via": "citation", "chunk_ids": []}
    return list(merged.values())


def _rule_summary(findings: list[RuleFinding]) -> tuple[str, ...]:
    return tuple(
        f"{f.rule_type}: {'passed' if f.passed else 'FAILED'} ({f.severity}) - {f.message}" for f in findings
    )


def _to_grader_output(call: JudgeCall | None, use_evidence: bool) -> GraderOutput | None:
    if call is None or call.output is None:
        return None
    out = call.output
    claims = []
    for claim in out.claims:
        verdict = "uncertain" if claim.verdict == "not_verifiable" else claim.verdict
        ids = list(claim.evidence_ids) if use_evidence else []
        claims.append(
            ClaimAssessment(
                claim=claim.claim,
                verdict=verdict,
                confidence=out.confidence if out.confidence is not None else 0.0,
                evidence_chunk_ids=ids,
                reason="judge claim assessment",
            )
        )
    return GraderOutput(
        verdict=out.verdict,
        severity="major" if out.verdict == "fail" else "no_issue",
        score=0.0 if out.verdict == "fail" else 1.0,
        confidence=out.confidence if out.confidence is not None else 0.0,
        reason=out.reason or "judge",
        claims=claims,
        needs_human_review=False,
    )


def _heuristic_grader_output(case: BenchmarkCase, evidence: list[dict]) -> GraderOutput:
    items = [{"chunk_id": e["doc_id"], "text": e["text"], "score": e["score"] or 0.0} for e in evidence]
    grade, _ = heuristic_grade(case.prompt, case.candidate_response, case.requirements, items)
    return grade


def evaluate_case(
    case: BenchmarkCase,
    spec: SystemSpec,
    *,
    corpus: list[CorpusDocument],
    judge: Judge | None,
    retrieval: RetrievalConfig,
    policy: ControlPolicy,
) -> tuple[dict, JudgeCall | None, JudgeRequest | None, list[dict]]:
    started = time.perf_counter()
    corpus_ids = {doc.doc_id for doc in corpus}

    findings = check_rules(case.candidate_response, case.requirements) if spec.use_rules else []
    failed_rules = [f for f in findings if not f.passed]

    evidence = gather_evidence(case, corpus, retrieval) if spec.use_retrieval else []
    invalid_citations = (
        [cid for cid in cited_ids(case.candidate_response) if cid not in corpus_ids] if spec.use_retrieval else []
    )

    call: JudgeCall | None = None
    request: JudgeRequest | None = None
    grader: GraderOutput | None = None
    if spec.judge_mode == "judge":
        if judge is None:
            raise ValueError(f"{spec.name} needs a judge backend")
        request = JudgeRequest(
            case_id=case.case_id,
            prompt=case.prompt,
            response=case.candidate_response,
            evidence=tuple(evidence),
            rule_summary=_rule_summary(findings),
            grounded=spec.use_retrieval,
            show_rules=spec.use_rules,
        )
        call = judge.judge(request)
        grader = _to_grader_output(call, spec.use_retrieval)
    elif spec.judge_mode == "heuristic_grader":
        grader = _heuristic_grader_output(case, evidence)

    controls = None
    if spec.use_routing and grader is not None:
        policy_used = policy if spec.use_retrieval else policy.model_copy(
            update={"min_citation_coverage": 0.0, "block_on_invalid_citation": False}
        )
        evidence_for_controls = [{"chunk_id": e["doc_id"], "score": e["score"] or 0.0} for e in evidence]
        controls = evaluate_controls(grader, findings, evidence_for_controls, policy_used)

    reasons: list[str] = []
    category = "none"
    if failed_rules:
        reasons.append("rule:" + ",".join(f.rule_type for f in failed_rules))
        category = RULE_CATEGORY.get(failed_rules[0].rule_type, "other")
    if invalid_citations:
        reasons.append("invalid_citation:" + ",".join(invalid_citations))
        if category == "none":
            category = "hallucination"
    deterministic_fail = bool(reasons)

    judge_label: str | None = None
    judge_confidence: float | None = None
    if spec.judge_mode == "judge":
        if call is not None and call.output is not None:
            judge_label = call.output.verdict
            judge_confidence = call.output.confidence
    elif spec.judge_mode == "heuristic_grader" and grader is not None:
        judge_label = "fail" if grader.verdict in {"fail", "review"} else "pass"
        judge_confidence = grader.confidence

    if deterministic_fail:
        label: str | None = "fail"
    elif spec.judge_mode == "none":
        label = "pass"
    elif judge_label is None:
        label = None
    else:
        label = judge_label
        if judge_label == "fail":
            reasons.append("judge:fail")
            if spec.judge_mode == "judge" and call is not None and call.output is not None:
                category = call.output.failure_category
            else:
                category = "unsupported_claim"
        if controls is not None and controls.action == "block" and label == "pass":
            blocking = [f.control for f in controls.findings if f.action == "block"]
            label = "fail"
            reasons.append("controls:block:" + ",".join(blocking))
            category = "factual_error" if "claim_contradiction" in blocking else "retrieval_grounding_failure"

    routed = False
    route_reasons: list[str] = []
    if spec.use_routing and not deterministic_fail and spec.judge_mode != "none":
        if label is None:
            route_reasons.append("judge_output_unusable")
        if controls is not None and controls.action == "review":
            route_reasons.extend(f.control for f in controls.findings if not f.passed and f.action == "review")
        routed = bool(route_reasons)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    judge_latency = call.latency_ms if call is not None else None
    local_ms = elapsed_ms - (judge_latency or 0.0) if call is not None and not call.cache_hit else elapsed_ms
    prediction = {
        "case_id": case.case_id,
        "system": spec.name,
        "gold_label": case.gold_label,
        "gold_category": case.failure_category,
        "predicted_label": label,
        "predicted_category": category if label == "fail" else ("none" if label == "pass" else None),
        "correct": label == case.gold_label,
        "decision_reasons": reasons,
        "routed_to_human": routed,
        "route_reasons": route_reasons,
        "judge_label": judge_label,
        "judge_confidence": judge_confidence,
        "judge_category": call.output.failure_category if call is not None and call.output is not None else None,
        "judge_reason": call.output.reason if call is not None and call.output is not None else None,
        "judge_request_sha256": call.request_sha256 if call is not None else None,
        "judge_cache_hit": call.cache_hit if call is not None else None,
        "judge_parse_error": call.parse_error if call is not None else None,
        "judge_call_error": call.call_error if call is not None else None,
        "failed_rules": [f.model_dump() for f in failed_rules],
        "invalid_citations": invalid_citations,
        "evidence_ids": [e["doc_id"] for e in evidence],
        "gold_evidence_ids": list(case.gold_evidence_ids),
        "controls_action": controls.action if controls is not None else None,
        "controls_failed": [f.control for f in controls.findings if not f.passed] if controls is not None else [],
        "latency_ms": round(local_ms + (judge_latency or 0.0), 3),
        "judge_latency_ms": judge_latency,
        "cost_usd": call.cost_usd if call is not None else (0.0 if spec.judge_mode != "judge" else None),
        "ambiguous": case.ambiguous,
    }
    return prediction, call, request, evidence

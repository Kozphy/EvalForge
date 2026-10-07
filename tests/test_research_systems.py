import json

from app.controls import ControlPolicy
from research.dataset import BenchmarkCase, case_content_hash, load_corpus, load_split
from research.judge import JudgeCall, JudgeRequest, _finish
from research.systems import SYSTEMS, RetrievalConfig, cited_ids, evaluate_case, gather_evidence

CORPUS = load_corpus()
DEV = {c.case_id: c for c in load_split("dev")}
POLICY = ControlPolicy(min_confidence=0.7)
RETRIEVAL = RetrievalConfig()


class FakeJudge:
    backend = "fake"
    is_llm = False

    def __init__(self, raw: str):
        self.raw = raw
        self.requests: list[JudgeRequest] = []

    def judge(self, request: JudgeRequest) -> JudgeCall:
        self.requests.append(request)
        return _finish(JudgeCall(request_sha256=request.prompt_sha256(), raw_text=self.raw, output=None,
                                 cost_usd=0.0, backend=self.backend))


def _judge(verdict="pass", category="none", confidence=0.9, claims=None):
    return FakeJudge(json.dumps({"verdict": verdict, "failure_category": category, "confidence": confidence,
                                 "reason": "test", "claims": claims or []}))


def _case(**overrides) -> BenchmarkCase:
    row = DEV["EFB-001"].model_dump(mode="json")
    row.update(overrides)
    row["content_sha256"] = case_content_hash(row)
    return BenchmarkCase.model_validate(row)


def _run(case, system, judge=None):
    pred, call, request, evidence = evaluate_case(
        case, SYSTEMS[system], corpus=CORPUS, judge=judge, retrieval=RETRIEVAL, policy=POLICY
    )
    return pred, request, evidence


def test_cited_ids_extracts_unique_kb_ids():
    assert cited_ids("a [KB-01] b [KB-01] c [KB-07] (KB-02)") == ["KB-01", "KB-07"]


def test_grounding_retrieves_gold_evidence_and_resolves_citations():
    evidence = gather_evidence(DEV["EFB-019"], CORPUS, RETRIEVAL)
    assert "KB-07" in [e["doc_id"] for e in evidence]
    # EFB-007 cites KB-06 although KB-04 supports the claim: both must reach the judge.
    evidence = {e["doc_id"]: e for e in gather_evidence(DEV["EFB-007"], CORPUS, RETRIEVAL)}
    assert "KB-06" in evidence and "KB-04" in evidence
    assert all(e["text"] for e in evidence.values())


def test_b1_rule_failure_fails_and_clean_case_passes():
    pred, _, _ = _run(DEV["EFB-014"], "B1_deterministic")
    assert pred["predicted_label"] == "fail"
    assert pred["predicted_category"] == "format_error"
    pred, _, _ = _run(DEV["EFB-001"], "B1_deterministic")
    assert pred["predicted_label"] == "pass" and pred["judge_label"] is None


def test_rule_failure_is_final_even_if_judge_passes():
    pred, request, _ = _run(DEV["EFB-012"], "B4_hybrid", _judge("pass"))
    assert pred["predicted_label"] == "fail"
    assert pred["routed_to_human"] is False
    assert request.show_rules and "FAILED" in request.user_message()


def test_nonexistent_citation_is_deterministic_hallucination():
    case = _case(candidate_response="Land is not depreciated [KB-14].")
    pred, _, _ = _run(case, "B4_hybrid", _judge("pass"))
    assert pred["predicted_label"] == "fail"
    assert pred["predicted_category"] == "hallucination"
    assert pred["invalid_citations"] == ["KB-14"]
    # Without retrieval the citation check is disabled (ablation A2).
    pred, _, _ = _run(case, "A2_minus_retrieval", _judge("pass"))
    assert pred["predicted_label"] == "pass"


def test_low_confidence_pass_is_routed_but_label_kept():
    pred, _, _ = _run(DEV["EFB-001"], "B4_hybrid", _judge("pass", confidence=0.4))
    assert pred["predicted_label"] == "pass"
    assert pred["routed_to_human"] is True
    assert "grader_confidence" in pred["route_reasons"]
    pred, _, _ = _run(DEV["EFB-001"], "A4_minus_routing", _judge("pass", confidence=0.4))
    assert pred["routed_to_human"] is False


def test_contradicted_claim_blocks_a_pass_verdict():
    claims = [{"claim": "Land is depreciated", "verdict": "contradicted", "evidence_ids": ["KB-01"]}]
    pred, _, _ = _run(DEV["EFB-001"], "B4_hybrid", _judge("pass", claims=claims))
    assert pred["predicted_label"] == "fail"
    assert pred["predicted_category"] == "factual_error"
    # B3 has no controls layer: the judge verdict stands.
    pred, _, _ = _run(DEV["EFB-001"], "B3_grounded_judge", _judge("pass", claims=claims))
    assert pred["predicted_label"] == "pass"


def test_unparseable_judge_output_abstains_and_routes():
    pred, _, _ = _run(DEV["EFB-001"], "B4_hybrid", FakeJudge("not json"))
    assert pred["predicted_label"] is None
    assert pred["routed_to_human"] is True
    assert pred["judge_parse_error"]
    pred, _, _ = _run(DEV["EFB-001"], "B2_single_judge", FakeJudge("not json"))
    assert pred["predicted_label"] is None and pred["routed_to_human"] is False


def test_single_judge_sees_no_evidence_and_no_rules():
    judge = _judge()
    _, request, evidence = _run(DEV["EFB-001"], "B2_single_judge", judge)
    assert evidence == [] and not request.grounded and not request.show_rules


def test_minus_judge_ablation_uses_heuristic_grader_without_judge_calls():
    pred, request, _ = _run(DEV["EFB-001"], "A3_minus_judge", None)
    assert request is None
    assert pred["predicted_label"] in {"pass", "fail"}

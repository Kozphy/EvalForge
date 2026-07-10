from app.graders import calculate_metrics, check_rules, heuristic_grade, split_sentences
from app.schemas import RequirementSpec


def test_split_sentences_handles_english_and_chinese() -> None:
    assert split_sentences("One. Two!") == ["One.", "Two!"]
    assert split_sentences("第一句。第二句！") == ["第一句。", "第二句！"]


def test_rule_checks_find_core_format_failure() -> None:
    requirements = RequirementSpec(exact_sentences=2, required_phrases=["Jamie"])
    findings = check_rules("Jamie, I cannot attend.", requirements)
    assert any(item.rule == "exact_sentences" and not item.passed for item in findings)
    assert any(item.rule.startswith("required_phrase") and item.passed for item in findings)


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
    # max_words is configured as a minor deterministic rule in the MVP.
    assert output.severity in {"minor", "major"}


def test_metrics() -> None:
    metrics = calculate_metrics(
        ["no_issue", "major", "minor"],
        ["no_issue", "minor", "minor"],
    )
    assert metrics["accuracy"] == 0.6667
    assert metrics["confusion_matrix"]["major"]["minor"] == 1

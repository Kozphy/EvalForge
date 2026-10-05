"""Human review records and judge–human agreement helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finance_eval.schema import HumanRubricScores


def load_reviews(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["case_id"]] = row
    return out


def agreement_rate(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    agree = sum(1 for a, b in pairs if a == b)
    return agree / len(pairs)


def seed_human_reviews(case_results: list[dict[str, Any]], path: Path, sample_n: int = 20) -> list[dict[str, Any]]:
    """Create a small adjudicated review set for disagreement measurement.

    Human decisions follow deterministic ground truth for seeded reviews
    (label: curated_seed), while judge may disagree when simulated.
    """
    selected = case_results[:sample_n]
    # Force one disagreement for pipeline demo: first failing case, human marks pass.
    disagree_id = next((item["case_id"] for item in selected if not item.get("passed")), None)
    rows: list[dict[str, Any]] = []
    for item in selected:
        passed = bool(item.get("passed"))
        decision = "pass" if passed else "fail"
        notes = "Seeded human review for portfolio agreement demo."
        if disagree_id and item.get("case_id") == disagree_id:
            decision = "pass"
            notes = "Intentional disagreement seed: human overrides deterministic fail."
        scores = HumanRubricScores(
            correctness=5 if decision == "pass" else 2,
            reasoning=4 if decision == "pass" else 2,
            completeness=4 if decision == "pass" else 2,
            domain_validity=5 if decision == "pass" else 2,
            evidence_quality=4 if decision == "pass" else 2,
            financial_risk="low" if decision == "pass" else "high",
            severity="none" if decision == "pass" else "high",
            decision=decision,  # type: ignore[arg-type]
            notes=notes,
        )
        rows.append(
            {
                "case_id": item["case_id"],
                "reviewer": "human.reviewer@example.com",
                "source": "curated_seed",
                **scores.model_dump(),
                "judge_decision": item.get("judge", {}).get("decision"),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return rows

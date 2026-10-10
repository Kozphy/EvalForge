"""Professional evaluation report generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finance_eval import DATASET_VERSION, PROMPT_VERSION
from finance_eval.taxonomy import TAXONOMY


def write_report(result: dict[str, Any], out_path: Path) -> Path:
    m = result["metrics"]
    policy = result["policy"]
    regression = result.get("regression") or {}
    manifest = result["manifest"]
    failures = m.get("failure_counts") or {}
    top_failures = sorted(
        ((k, v) for k, v in failures.items() if k != "FIN-NONE"),
        key=lambda kv: kv[1],
        reverse=True,
    )[:8]

    lines = [
        "# Finance + Accounting LLM Evaluation Report",
        "",
        f"**Dataset:** `{DATASET_VERSION}` · **Prompt version:** `{PROMPT_VERSION}`  ",
        f"**Run ID:** `{manifest.get('run_id')}` · **Model:** `{manifest.get('model')}` `{manifest.get('model_version')}`  ",
        f"**Policy decision:** `{policy.get('decision')}` · **Human review status:** `{manifest.get('human_review_status')}`",
        "",
        "## Executive Summary",
        "",
        "Financial AI systems can produce fluent answers that are materially wrong "
        "(misstated equity, unbalanced journals, cash/profit confusion, fabricated standards). "
        "This report evaluates a reproducible offline candidate against a versioned golden set "
        "using deterministic grading as the source of truth, with simulated judge scores and "
        "seeded human reviews for disagreement measurement.",
        "",
        f"- Cases evaluated: **{m.get('n_cases')}**",
        f"- Accuracy / pass rate: **{m.get('accuracy', 0):.1%}** (95% bootstrap CI {m.get('accuracy_ci95')})",
        f"- Hallucination rate (FIN-HALL-006): **{m.get('hallucination_rate', 0):.1%}**",
        f"- Critical error rate: **{m.get('critical_error_rate', 0):.1%}**",
        f"- Calculation error rate: **{m.get('calculation_error_rate', 0):.1%}**",
        f"- Policy: **{policy.get('decision')}** — {policy.get('rationale')}",
        "",
        "## Research Questions",
        "",
        "1. Can deterministic graders detect material finance/accounting errors without an LLM judge?",
        "2. Which failure classes dominate under a planted-error offline candidate?",
        "3. Do policy gates block release when critical financial error rates exceed thresholds?",
        "4. How often do simulated judge decisions disagree with seeded human reviews?",
        "",
        "## Dataset",
        "",
        f"- Version: `{DATASET_VERSION}`",
        f"- SHA256: `{manifest.get('dataset_sha256')}`",
        f"- Size: {m.get('n_cases')} original synthetic items (not copyrighted exam reproductions)",
        "- Categories: financial statements, journals, equations, revenue, expenses, margins, "
        "cash flow, ratios, audit, controls, reconciliation, anomalies, analysis, SQL, Python",
        "",
        "## Evaluation Methodology",
        "",
        "```text",
        "Input → Candidate Response → Parser → Deterministic Metrics",
        "     → Simulated Judge Rubric → Seeded Human Review",
        "     → Failure Taxonomy → Baseline Regression → Policy Gate → Audit Evidence",
        "```",
        "",
        "- **Deterministic-first:** numeric, exact text, journal JSON, SQL/Python result fixtures",
        "- **LLM-as-judge:** not required for this report; scores are labeled `simulated_heuristic_judge`",
        "- **Human review:** curated seed on a subset; disagreement tracked when present",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(m, indent=2),
        "```",
        "",
        "## Results",
        "",
        f"Passed {m.get('n_passed')} / {m.get('n_cases')}. "
        "Latency/cost are null for the offline fixture candidate (no live model calls).",
        "",
        "## Failure Analysis",
        "",
        "| Code | Name | Count |",
        "|---|---|---:|",
    ]
    for code, count in top_failures:
        name = (TAXONOMY.get(code) or {}).get("name", "")
        lines.append(f"| `{code}` | {name} | {count} |")
    if not top_failures:
        lines.append("| — | — | 0 |")

    lines.extend(
        [
            "",
            "## Ablation / Comparison",
            "",
            "Baseline comparison:",
            "",
            "```json",
            json.dumps(regression, indent=2),
            "```",
            "",
            "## Human-vs-Judge Agreement",
            "",
            f"- Seeded human reviews: **{result.get('n_human_reviews')}**",
            f"- Agreement rate (decision): **{result.get('judge_human_agreement')}**",
            "",
            "Agreement is measured only on the seeded subset. Do not extrapolate to production.",
            "",
            "## Cost and Latency",
            "",
            "- Offline fixture run: no token usage, no API cost.",
            "- Live model hooks can populate `latency_ms`, token counts, and `estimated_cost_usd` per case.",
            "",
            "## Threats to Validity",
            "",
            "- Candidate responses are embedded fixtures with planted errors (not a blind live model).",
            "- Judge is simulated from deterministic outcomes (not independent).",
            "- SQL/Python grading checks numeric results, not sandboxed execution of arbitrary code.",
            "- Human reviews are curated seeds for pipeline demonstration.",
            "",
            "## Limitations",
            "",
            "- Not production financial advice or audit assurance.",
            "- Golden set is small (~100–200) and synthetic.",
            "- No claim of GAAP/IFRS certification coverage.",
            "",
            "## Governance Implications",
            "",
            "- Critical accounting and hallucination rates can force **FAIL** or **HUMAN_REVIEW_REQUIRED**.",
            "- Evidence manifests include dataset hash, metrics, failure classes, and policy decision.",
            "- Deterministic checks remain authoritative over fluent LLM rationales.",
            "",
            "## Reproduction Instructions",
            "",
            "```bash",
            "python -m finance_eval generate-dataset",
            "python -m finance_eval run --write-baseline",
            "python -m finance_eval report",
            "pytest tests/test_finance_eval.py -q",
            "```",
            "",
            "## Maturity Labels",
            "",
            "| Component | Label |",
            "|---|---|",
            "| Dataset | implemented |",
            "| Deterministic grading | implemented |",
            "| LLM judge | simulated |",
            "| Human review seed | curated_seed |",
            "| Policy gate | implemented |",
            "| Evidence JSON/JSONL | implemented (file append) |",
            "| Production adoption | not claimed |",
            "",
        ]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path

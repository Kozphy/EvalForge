"""Metrics aggregation, paired comparisons, disagreement records, and the run report."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median

from research.metrics import (
    bootstrap_confidence_intervals,
    classification_metrics,
    cohen_kappa,
    mcnemar_exact,
    paired_bootstrap,
    percentile,
)
from research.systems import ABLATIONS, PRIMARY_SYSTEMS, SYSTEMS
from research.taxonomy import FAILURE_CATEGORIES

OVERCONFIDENT_THRESHOLD = 0.8


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def _latency(values: list[float | None]) -> dict:
    measured = sorted(v for v in values if v is not None)
    if not measured:
        return {"mean": None, "p50": None, "p95": None, "note": "NOT MEASURED"}
    return {
        "mean": round(mean(measured), 3),
        "p50": round(median(measured), 3),
        "p95": round(percentile(measured, 0.95), 3),
        "unit": "ms wall-clock per case (local compute + judge API latency; cache hits use original call latency)",
    }


def _cost(preds: list[dict], judge_is_llm: bool) -> dict:
    costs = [p["cost_usd"] for p in preds]
    if any(c is None for c in costs):
        return {
            "cost_per_case_usd": None,
            "note": "NOT MEASURED: at least one judge call has no cost estimate (call failed or model not priced)",
        }
    uses_judge = any(p["judge_request_sha256"] for p in preds)
    basis = (
        "estimated from finance_eval.live.PRICE_PER_1M token prices (not a provider invoice)"
        if uses_judge and judge_is_llm
        else "no paid API calls (local computation only)"
    )
    return {"cost_per_case_usd": round(sum(costs) / len(costs), 8), "basis": basis}


def system_metrics(system: str, preds: list[dict], judge_is_llm: bool) -> dict:
    spec = SYSTEMS[system]
    gold = [p["gold_label"] for p in preds]
    pred = [p["predicted_label"] for p in preds]
    n = len(preds)
    automated = classification_metrics(gold, pred)

    judged = [p for p in preds if p["judge_label"] is not None]
    if spec.judge_mode == "none":
        agreement = {"value": None, "note": "not applicable: system has no judge"}
    else:
        agreement = {
            "value": _rate(sum(1 for p in judged if p["judge_label"] == p["gold_label"]), len(judged)),
            "cohen_kappa": cohen_kappa([p["judge_label"] for p in judged], [p["gold_label"] for p in judged]),
            "n_judged": len(judged),
            "note": "raw judge verdict vs author gold label, before rules/controls are applied",
        }

    out: dict = {
        "label": spec.label,
        "description": spec.description,
        "components": {
            "rules": spec.use_rules,
            "retrieval": spec.use_retrieval,
            "judge": spec.judge_mode,
            "routing": spec.use_routing,
        },
        "n": n,
        "automated": automated,
        "abstention_rate": automated["abstained"] / n,
        "human_review_rate": (sum(1 for p in preds if p["routed_to_human"]) / n) if spec.use_routing else 0.0,
        "routing_enabled": spec.use_routing,
        "judge_human_agreement": agreement,
        "judge_parse_failures": sum(1 for p in preds if p["judge_parse_error"]),
        "judge_call_failures": sum(1 for p in preds if p["judge_call_error"]),
        "latency_ms": _latency([p["latency_ms"] for p in preds]),
        **_cost(preds, judge_is_llm),
    }

    if spec.use_routing:
        routed = [p for p in preds if p["routed_to_human"]]
        errors = [p for p in preds if not p["correct"]]
        errors_routed = [p for p in errors if p["routed_to_human"]]
        kept = [p for p in preds if not p["routed_to_human"]]
        out["review"] = {
            "routed": len(routed),
            "automated_errors": len(errors),
            "errors_routed": len(errors_routed),
            "error_capture_rate": _rate(len(errors_routed), len(errors)),
            "routing_precision": _rate(len(errors_routed), len(routed)),
            "unreviewed_errors": len(errors) - len(errors_routed),
            "coverage": len(kept) / n,
            "selective_on_unrouted": (
                classification_metrics([p["gold_label"] for p in kept], [p["predicted_label"] for p in kept])
                if kept
                else None
            ),
            "oracle_resolved": classification_metrics(
                gold, [p["gold_label"] if p["routed_to_human"] else p["predicted_label"] for p in preds]
            ),
            "oracle_note": "SIMULATED upper bound: routed cases receive the gold label (perfect reviewer). "
            "Not measured human performance.",
        }

    per_category: dict[str, dict] = {}
    for category in FAILURE_CATEGORIES:
        members = [p for p in preds if p["gold_category"] == category]
        if members:
            detected = sum(1 for p in members if p["predicted_label"] == "fail")
            per_category[category] = {"n": len(members), "detected": detected, "recall": detected / len(members)}
    out["per_category_recall"] = per_category

    true_pos = [p for p in preds if p["gold_label"] == "fail" and p["predicted_label"] == "fail"]
    out["category_accuracy_on_true_positives"] = {
        "value": _rate(sum(1 for p in true_pos if p["predicted_category"] == p["gold_category"]), len(true_pos)),
        "n": len(true_pos),
    }

    if spec.use_retrieval:
        hits = [set(p["gold_evidence_ids"]) <= set(p["evidence_ids"]) for p in preds]
        out["gold_evidence_recall"] = {"value": sum(hits) / n, "n": n,
                                       "note": "share of cases whose gold evidence documents were all in the evidence set"}

    amb = [p for p in preds if p["ambiguous"]]
    clear = [p for p in preds if not p["ambiguous"]]
    out["accuracy_by_ambiguity"] = {
        "ambiguous": {"n": len(amb), "accuracy": _rate(sum(p["correct"] for p in amb), len(amb))},
        "unambiguous": {"n": len(clear), "accuracy": _rate(sum(p["correct"] for p in clear), len(clear))},
    }
    return out


def comparisons(by_system: dict[str, list[dict]], iterations: int, seed: int) -> dict:
    out: dict = {}
    pairs: list[tuple[str, str, str]] = []
    if "B4_hybrid" in by_system:
        for baseline in ("B1_deterministic", "B2_single_judge", "B3_grounded_judge"):
            if baseline in by_system:
                pairs.append((baseline, "B4_hybrid", f"B4_hybrid_vs_{baseline}"))
        for ablation in ABLATIONS:
            if ablation in by_system:
                pairs.append(("B4_hybrid", ablation, f"{ablation}_vs_B4_hybrid"))
    if "B2_single_judge" in by_system and "B3_grounded_judge" in by_system:
        pairs.append(("B2_single_judge", "B3_grounded_judge", "B3_grounded_judge_vs_B2_single_judge"))

    for a, b, key in pairs:
        gold = [p["gold_label"] for p in by_system[a]]
        assert [p["case_id"] for p in by_system[a]] == [p["case_id"] for p in by_system[b]]
        pa = [p["predicted_label"] for p in by_system[a]]
        pb = [p["predicted_label"] for p in by_system[b]]
        out[key] = {
            "system_a": a,
            "system_b": b,
            "direction": "difference = system_b - system_a",
            "paired_bootstrap": paired_bootstrap(gold, pa, pb, iterations=iterations, seed=seed),
            "mcnemar_exact": mcnemar_exact(gold, pa, pb),
        }
    return out


def confidence_intervals(by_system: dict[str, list[dict]], iterations: int, seed: int) -> dict:
    return {
        system: bootstrap_confidence_intervals(
            [p["gold_label"] for p in preds], [p["predicted_label"] for p in preds], iterations=iterations, seed=seed
        )
        for system, preds in by_system.items()
    }


def _disagreement_tags(p: dict) -> list[str]:
    tags: list[str] = []
    spec = SYSTEMS[p["system"]]
    if p["predicted_label"] is None:
        tags.append("abstained_judge_output_unusable")
    elif p["gold_label"] == "pass":
        reasons = " ".join(p["decision_reasons"])
        if "rule:" in reasons:
            tags.append("rule_false_positive")
        if "invalid_citation:" in reasons:
            tags.append("citation_check_false_positive")
        if "controls:block" in reasons:
            tags.append("controls_block_false_positive")
        if "judge:fail" in reasons:
            tags.append("judge_false_positive")
    else:
        tags.append("missed_by_rules" if spec.judge_mode == "none" else "judge_false_negative")
    if spec.use_retrieval and not set(p["gold_evidence_ids"]) <= set(p["evidence_ids"]):
        tags.append("grounding_failure_gold_evidence_not_retrieved")
    if p["judge_confidence"] is not None and p["judge_confidence"] >= OVERCONFIDENT_THRESHOLD and (
        p["judge_label"] is not None and p["judge_label"] != p["gold_label"]
    ):
        tags.append("overconfident_judge_error")
    if p["ambiguous"]:
        tags.append("ambiguous_gold_label")
    return tags


def disagreements(predictions: list[dict], evidence_rows: dict[tuple[str, str], dict]) -> list[dict]:
    rows = []
    for p in predictions:
        if p["correct"]:
            continue
        tags = _disagreement_tags(p)
        ev = evidence_rows.get((p["system"], p["case_id"]))
        rows.append(
            {
                "case_id": p["case_id"],
                "system": p["system"],
                "human_label": p["gold_label"],
                "judge_label": p["judge_label"],
                "system_label": p["predicted_label"],
                "confidence": p["judge_confidence"],
                "confidence_note": "judge self-reported confidence; NOT a calibrated probability",
                "failure_category": p["gold_category"],
                "predicted_category": p["predicted_category"],
                "retrieved_evidence": (
                    [{"doc_id": e["doc_id"], "via": e["via"], "score": e["score"]} for e in ev["evidence"]]
                    if ev
                    else []
                ),
                "gold_evidence_ids": p["gold_evidence_ids"],
                "routed_to_human": p["routed_to_human"],
                "reason_for_disagreement": "; ".join(tags),
                "tags": tags,
                "decision_reasons": p["decision_reasons"],
                "judge_reason": p["judge_reason"],
                "ambiguous": p["ambiguous"],
            }
        )
    return rows


# ------------------------------------------------------------------ report


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _ci(cis: dict, system: str, metric: str) -> str:
    entry = cis[system][metric]
    if entry["point"] is None:
        return "n/a"
    return f"{entry['point']:.3f} [{_fmt(entry['ci_low'])}, {_fmt(entry['ci_high'])}]"


def render_report(manifest: dict, metrics: dict, cis: dict, comps: dict, disagreement_rows: list[dict]) -> str:
    judge = manifest["judge"]
    lines = [
        f"# Experiment report: `{manifest['experiment_id']}`",
        "",
        "Generated by `research.run` from the raw artifacts in this directory. Do not edit by hand.",
        "",
        f"- **Evidence label:** {manifest['evidence_label']}",
        f"- **Dataset:** {manifest['dataset']['name']} v{manifest['dataset']['version']} "
        f"(`{manifest['dataset']['dataset_sha256'][:12]}`), splits {manifest['dataset']['splits']}, "
        f"n={manifest['dataset']['n_cases']}, holdout used: {manifest['dataset']['holdout_used']}",
        f"- **Judge backend:** `{judge['backend']}` (is LLM: {judge['is_llm']}; model: {judge['model']}; "
        f"prompt {judge['prompt_version']})",
        f"- **Git:** `{manifest['git']['commit']}` (dirty: {manifest['git']['dirty']})",
        f"- **Seed:** {manifest['seed']}; bootstrap iterations: {manifest['bootstrap']['iterations']}",
        "",
    ]
    if not judge["is_llm"]:
        lines += [
            "> **The judge in this run is NOT an LLM.** B2, B3, B4, A1, A2 and A4 use the offline heuristic "
            "stand-in, so their numbers test the pipeline mechanics only. They are not evidence about LLM "
            "judging. Only the B1 (deterministic-only) results are a real measurement of that system.",
            "",
        ]

    systems = [s for s in (*PRIMARY_SYSTEMS, *ABLATIONS) if s in metrics]
    lines += [
        "## Primary metrics (automated decisions, 95% bootstrap CI)",
        "",
        "| System | Accuracy | Precision | Recall | Macro-F1 | FPR | FNR | Abstain | Review rate |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in systems:
        m = metrics[s]
        lines.append(
            f"| {m['label']} (`{s}`) | {_ci(cis, s, 'accuracy')} | {_ci(cis, s, 'precision')} | "
            f"{_ci(cis, s, 'recall')} | {_ci(cis, s, 'macro_f1')} | {_ci(cis, s, 'false_positive_rate')} | "
            f"{_ci(cis, s, 'false_negative_rate')} | {_fmt(m['abstention_rate'])} | {_fmt(m['human_review_rate'])} |"
        )

    lines += ["", "## Operational metrics", "",
              "| System | Judge-human agreement | Kappa | Latency p50 ms | Latency p95 ms | Cost/case USD | Parse failures |",
              "|---|---|---|---|---|---|---|"]
    for s in systems:
        m = metrics[s]
        ag = m["judge_human_agreement"]
        lines.append(
            f"| `{s}` | {_fmt(ag.get('value'))} | {_fmt(ag.get('cohen_kappa'))} | {_fmt(m['latency_ms']['p50'])} | "
            f"{_fmt(m['latency_ms']['p95'])} | {_fmt(m['cost_per_case_usd'], 6)} | {m['judge_parse_failures']} |"
        )

    routed_systems = [s for s in systems if "review" in metrics[s]]
    if routed_systems:
        lines += ["", "## Human-review routing", "",
                  "| System | Routed | Automated errors | Errors routed | Error capture | Routing precision | "
                  "Coverage | Selective acc. | Oracle-resolved acc. (simulated) |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for s in routed_systems:
            r = metrics[s]["review"]
            sel = r["selective_on_unrouted"]
            lines.append(
                f"| `{s}` | {r['routed']} | {r['automated_errors']} | {r['errors_routed']} | "
                f"{_fmt(r['error_capture_rate'])} | {_fmt(r['routing_precision'])} | {_fmt(r['coverage'])} | "
                f"{_fmt(sel['accuracy'] if sel else None)} | {_fmt(r['oracle_resolved']['accuracy'])} |"
            )

    if comps:
        lines += ["", "## Paired comparisons (difference = B - A; 95% paired bootstrap CI; exact McNemar)", "",
                  "| Comparison | Δ accuracy | Δ macro-F1 | Δ FPR | McNemar discordant (A only / B only) | p |",
                  "|---|---|---|---|---|---|"]
        for key, c in comps.items():
            pb = c["paired_bootstrap"]

            def d(metric: str) -> str:
                e = pb[metric]
                if e["difference_b_minus_a"] is None:
                    return "n/a"
                return f"{e['difference_b_minus_a']:+.3f} [{_fmt(e['ci_low'])}, {_fmt(e['ci_high'])}]"

            mc = c["mcnemar_exact"]
            lines.append(
                f"| {key} | {d('accuracy')} | {d('macro_f1')} | {d('false_positive_rate')} | "
                f"{mc['a_correct_b_wrong']} / {mc['a_wrong_b_correct']} | {mc['p_value']:.4f} |"
            )

    lines += ["", "## Recall by gold failure category", ""]
    cats = sorted({c for s in systems for c in metrics[s]["per_category_recall"]})
    lines.append("| Category | n | " + " | ".join(f"`{s}`" for s in systems) + " |")
    lines.append("|---|---|" + "---|" * len(systems))
    for cat in cats:
        n = next(metrics[s]["per_category_recall"][cat]["n"] for s in systems if cat in metrics[s]["per_category_recall"])
        cells = [
            f"{metrics[s]['per_category_recall'][cat]['detected']}/{n}" if cat in metrics[s]["per_category_recall"] else "-"
            for s in systems
        ]
        lines.append(f"| {cat} | {n} | " + " | ".join(cells) + " |")

    lines += ["", "## Error analysis", ""]
    for s in systems:
        rows = [r for r in disagreement_rows if r["system"] == s]
        tags = Counter(t for r in rows for t in r["tags"])
        fp = sum(1 for r in rows if r["human_label"] == "pass" and r["system_label"] == "fail")
        fn = sum(1 for r in rows if r["human_label"] == "fail" and r["system_label"] == "pass")
        ab = sum(1 for r in rows if r["system_label"] is None)
        tag_text = ", ".join(f"{k}={v}" for k, v in sorted(tags.items())) or "none"
        lines.append(f"- `{s}`: {len(rows)} disagreements (FP {fp}, FN {fn}, abstained {ab}); tags: {tag_text}")

    b4 = [r for r in disagreement_rows if r["system"] == "B4_hybrid"]
    if b4:
        lines += ["", "### Every B4 hybrid disagreement", "",
                  "| Case | Gold | System | Judge | Conf. | Gold category | Routed | Reason |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in b4:
            lines.append(
                f"| {r['case_id']} | {r['human_label']} | {_fmt(r['system_label'])} | {_fmt(r['judge_label'])} | "
                f"{_fmt(r['confidence'], 2)} | {r['failure_category']} | {r['routed_to_human']} | "
                f"{r['reason_for_disagreement']} |"
            )

    lines += [
        "",
        "## Reading these numbers",
        "",
        "- The cases are synthetic and labelled by one author (E0). The same person wrote the rules and the evaluator.",
        "- n is small. Overlapping confidence intervals mean the systems are not distinguishable at this sample size.",
        "- Judge confidence is self-reported and uncalibrated. 'Overconfident' means confidence ≥ "
        f"{OVERCONFIDENT_THRESHOLD} on a wrong verdict.",
        "- Oracle-resolved accuracy assumes a perfect human reviewer and is an upper bound, not a measurement.",
        "",
    ]
    return "\n".join(lines)


def group_by_system(predictions: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for p in predictions:
        grouped[p["system"]].append(p)
    return dict(grouped)

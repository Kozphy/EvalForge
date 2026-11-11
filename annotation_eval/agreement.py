"""Inter-annotator agreement and adjudication.

Agreement is only meaningful between *independent* annotators. These helpers
compute the numbers; whether the inputs are human, simulated, or seeded is
carried through from :class:`~annotation_eval.schema.Annotation.provenance`
and reported alongside the statistic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from annotation_eval.schema import HUMAN_PROVENANCES, Annotation, LabeledItem, LabelProvenance


def _paired(a: Sequence[str], b: Sequence[str]) -> List[Tuple[str, str]]:
    if len(a) != len(b):
        raise ValueError("annotation sequences must have the same length")
    if not a:
        raise ValueError("at least one paired item is required")
    return list(zip(a, b))


def percent_agreement(a: Sequence[str], b: Sequence[str]) -> float:
    """Share of items on which two annotators chose the same label."""
    pairs = _paired(a, b)
    return sum(1 for x, y in pairs if x == y) / len(pairs)


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa for two annotators over the same items.

    ``kappa = (p_o - p_e) / (1 - p_e)``. When both annotators use one single
    identical label for every item (``p_e == 1``) kappa is undefined, so a
    ``ValueError`` is raised instead of reporting a misleading value.
    """
    pairs = _paired(a, b)
    n = len(pairs)
    p_o = sum(1 for x, y in pairs if x == y) / n
    count_a = Counter(x for x, _ in pairs)
    count_b = Counter(y for _, y in pairs)
    p_e = sum((count_a[label] / n) * (count_b[label] / n) for label in set(count_a) | set(count_b))
    if p_e == 1.0:
        raise ValueError("kappa undefined: both annotators used a single identical label for every item")
    return (p_o - p_e) / (1 - p_e)


def _by_annotator(annotations: Iterable[Annotation]) -> Dict[str, Dict[str, Annotation]]:
    table: Dict[str, Dict[str, Annotation]] = defaultdict(dict)
    for ann in annotations:
        if ann.item_id in table[ann.annotator_id]:
            raise ValueError(f"duplicate annotation for {ann.annotator_id}/{ann.item_id}")
        table[ann.annotator_id][ann.item_id] = ann
    return table


def pairwise_agreement(annotations: Iterable[Annotation], annotator_a: str, annotator_b: str) -> dict:
    """Percent agreement and Cohen's kappa on the items both annotators labelled."""
    annotations = list(annotations)
    table = _by_annotator(annotations)
    if annotator_a == annotator_b:
        raise ValueError("agreement requires two different annotators")
    for name in (annotator_a, annotator_b):
        if name not in table:
            raise ValueError(f"unknown annotator: {name}")
    shared = sorted(set(table[annotator_a]) & set(table[annotator_b]))
    a = [table[annotator_a][i].label for i in shared]
    b = [table[annotator_b][i].label for i in shared]
    provenances = sorted({table[annotator_a][i].provenance.value for i in shared} | {table[annotator_b][i].provenance.value for i in shared})
    human = all(LabelProvenance(p) in HUMAN_PROVENANCES for p in provenances)
    try:
        kappa: Optional[float] = round(cohen_kappa(a, b), 4)
    except ValueError:
        kappa = None
    return {
        "annotator_a": annotator_a,
        "annotator_b": annotator_b,
        "n_shared_items": len(shared),
        "percent_agreement": round(percent_agreement(a, b), 4),
        "cohen_kappa": kappa,
        "provenance": provenances,
        "is_human_agreement": human,
        "disagreements": [
            {"item_id": i, annotator_a: table[annotator_a][i].label, annotator_b: table[annotator_b][i].label}
            for i in shared
            if table[annotator_a][i].label != table[annotator_b][i].label
        ],
    }


def adjudicate(
    annotations: Iterable[Annotation],
    texts: Mapping[str, str],
    adjudicator_decisions: Optional[Mapping[str, str]] = None,
    adjudicator_id: Optional[str] = None,
) -> List[LabeledItem]:
    """Build gold labels from multiple annotations.

    * Unanimous items take the shared label.
    * Non-unanimous items require an explicit adjudicator decision; there is
      no silent majority vote. Missing decisions raise ``ValueError`` listing
      the unresolved item ids.
    * Output provenance is ``ADJUDICATED_HUMAN`` only when every input
      annotation (and the adjudicator) is human; otherwise the weakest input
      provenance is kept so simulated data never becomes "human".
    """
    decisions = dict(adjudicator_decisions or {})
    if decisions and not adjudicator_id:
        raise ValueError("adjudicator_id is required when adjudicator decisions are supplied")
    per_item: Dict[str, List[Annotation]] = defaultdict(list)
    for ann in annotations:
        per_item[ann.item_id].append(ann)
    unresolved = sorted(
        item_id for item_id, anns in per_item.items() if len({a.label for a in anns}) > 1 and item_id not in decisions
    )
    if unresolved:
        raise ValueError(f"unresolved disagreements need adjudication: {unresolved}")
    gold: List[LabeledItem] = []
    for item_id in sorted(per_item):
        anns = per_item[item_id]
        if item_id not in texts:
            raise ValueError(f"missing text for item {item_id}")
        provenances = {a.provenance for a in anns}
        all_human = provenances <= HUMAN_PROVENANCES
        if len({a.label for a in anns}) == 1:
            label = anns[0].label
            notes = f"unanimous ({len(anns)} annotators)"
            annotator = None
        else:
            label = decisions[item_id]
            notes = "adjudicated disagreement: " + ", ".join(f"{a.annotator_id}={a.label}" for a in anns)
            annotator = adjudicator_id
        if all_human:
            provenance = LabelProvenance.ADJUDICATED_HUMAN
        else:
            non_human = sorted(p.value for p in provenances if p not in HUMAN_PROVENANCES)
            provenance = LabelProvenance(non_human[0])
        gold.append(
            LabeledItem(
                item_id=item_id,
                text=texts[item_id],
                gold_label=label,
                provenance=provenance,
                annotator_id=annotator,
                notes=notes,
            )
        )
    return gold

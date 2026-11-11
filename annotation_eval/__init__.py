"""Label-provenance-aware classification, agreement, and rubric evaluation.

Every label and prediction in this package carries an explicit provenance so
that synthetic, seeded, rule-based, model-generated, and independent human
labels can never be silently mixed up. The bundled datasets are SYNTHETIC
fixtures written for unit tests; they are not human annotations and not a
benchmark.
"""

from annotation_eval.schema import (
    LabelProvenance,
    LabeledItem,
    Prediction,
    PredictorKind,
)

__all__ = ["LabelProvenance", "LabeledItem", "Prediction", "PredictorKind"]

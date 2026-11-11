"""Schemas that make label provenance explicit."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LabelProvenance(str, Enum):
    """Where a gold label came from.

    Only ``HUMAN_INDEPENDENT`` and ``ADJUDICATED_HUMAN`` describe labels
    produced by people who did not see the system's predictions. Everything
    else must be reported as non-human or non-independent.
    """

    SYNTHETIC_AUTHOR = "synthetic_author"  # written by the dataset author together with the item
    SEEDED_DEMO = "seeded_demo"  # demo rows planted to illustrate a workflow
    RULE_BASED = "rule_based"  # produced by deterministic rules
    MODEL_GENERATED = "model_generated"  # produced by an ML model or LLM
    SIMULATED_ANNOTATOR = "simulated_annotator"  # scripted stand-in for a human annotator
    HUMAN_INDEPENDENT = "human_independent"  # a person labelling blind to predictions
    ADJUDICATED_HUMAN = "adjudicated_human"  # human adjudication of independent human labels


HUMAN_PROVENANCES = frozenset({LabelProvenance.HUMAN_INDEPENDENT, LabelProvenance.ADJUDICATED_HUMAN})


class PredictorKind(str, Enum):
    """What produced a prediction. A rule-based baseline is never an ML model."""

    RULE_BASED = "rule_based"
    TRAINED_ML = "trained_ml"
    LLM = "llm"
    HUMAN = "human"


class LabeledItem(BaseModel):
    """One item with a gold label and the provenance of that label."""

    item_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    gold_label: str = Field(min_length=1)
    provenance: LabelProvenance
    annotator_id: Optional[str] = None
    notes: str = ""

    @field_validator("annotator_id")
    @classmethod
    def _no_fake_emails(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value.endswith("@example.com"):
            raise ValueError("placeholder e-mail addresses must not be used as annotator identities")
        return value

    @property
    def is_human_label(self) -> bool:
        return self.provenance in HUMAN_PROVENANCES


class Prediction(BaseModel):
    """One system prediction for an item."""

    item_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    predictor: str = Field(min_length=1)
    predictor_kind: PredictorKind


class Annotation(BaseModel):
    """One annotator's label for one item (used for agreement studies)."""

    item_id: str = Field(min_length=1)
    annotator_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    provenance: LabelProvenance

    @field_validator("annotator_id")
    @classmethod
    def _no_fake_emails(cls, value: str) -> str:
        if value.endswith("@example.com"):
            raise ValueError("placeholder e-mail addresses must not be used as annotator identities")
        return value

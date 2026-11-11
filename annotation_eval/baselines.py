"""Transparent RULE-BASED baselines for sentiment and content moderation.

These are keyword/regex heuristics, not trained ML classifiers. They exist so
that the evaluation harness has a reproducible, offline predictor to score;
their numbers on the bundled synthetic fixtures say nothing about real-world
sentiment or moderation quality.
"""

from __future__ import annotations

import re
from typing import Iterable, List

from annotation_eval.schema import LabeledItem, Prediction, PredictorKind

SENTIMENT_LABELS = ("negative", "neutral", "positive")
MODERATION_LABELS = ("allow", "harassment", "spam", "personal_data")

_POSITIVE = {
    "great", "excellent", "love", "loved", "helpful", "fast", "happy", "recommend", "perfect",
    "smooth", "friendly", "works", "clear", "pleased", "fantastic", "reliable",
}
_NEGATIVE = {
    "terrible", "awful", "hate", "broken", "slow", "useless", "disappointed", "refund", "worst",
    "crashed", "rude", "confusing", "late", "poor", "failed", "angry",
}
_NEGATORS = {"not", "never", "no", "hardly", "isn't", "wasn't", "don't", "didn't"}
_TOKEN = re.compile(r"[a-z']+")


def sentiment_rule_based(text: str) -> str:
    """Lexicon score with one-token negation flip. Returns a SENTIMENT_LABELS value."""
    tokens = _TOKEN.findall(text.lower())
    score = 0
    for index, token in enumerate(tokens):
        polarity = 1 if token in _POSITIVE else -1 if token in _NEGATIVE else 0
        if polarity and index > 0 and tokens[index - 1] in _NEGATORS:
            polarity = -polarity
        score += polarity
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return "neutral"


_HARASSMENT = re.compile(r"\b(idiot|stupid|loser|shut up|pathetic|nobody likes you|worthless)\b", re.I)
_SPAM = re.compile(r"(click (here|this link)|free (gift|money|crypto)|limited offer|you have won|act now|bit\.ly/)", re.I)
_PHONE = re.compile(r"\b\d{3}[-. ]\d{3,4}[-. ]\d{4}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_ID_NUMBER = re.compile(r"\b(passport|ssn|id number|credit card)\b[^.]*\d{4}", re.I)


def moderation_rule_based(text: str) -> str:
    """Return the first matching policy label in severity order, else ``allow``."""
    if _HARASSMENT.search(text):
        return "harassment"
    if _PHONE.search(text) or _EMAIL.search(text) or _ID_NUMBER.search(text):
        return "personal_data"
    if _SPAM.search(text):
        return "spam"
    return "allow"


def predict(items: Iterable[LabeledItem], task: str) -> List[Prediction]:
    """Run the rule-based baseline for ``task`` ("sentiment" or "moderation")."""
    if task == "sentiment":
        fn, name = sentiment_rule_based, "sentiment_lexicon_rules_v1"
    elif task == "moderation":
        fn, name = moderation_rule_based, "moderation_regex_rules_v1"
    else:
        raise ValueError(f"unknown task: {task}")
    return [
        Prediction(item_id=item.item_id, label=fn(item.text), predictor=name, predictor_kind=PredictorKind.RULE_BASED)
        for item in items
    ]

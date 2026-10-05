"""Finance + accounting + coding evaluation vertical for EvalForge.

Layers: dataset → runner → deterministic graders → (optional) judge →
human review → taxonomy → regression/policy → evidence → report.

Deterministic evaluation is the source of truth for CI. LLM-as-a-judge is
optional and never sole authority.
"""

from __future__ import annotations

__version__ = "1.0.0"
DATASET_VERSION = "finance-accounting-v1"
PROMPT_VERSION = "finance-eval-prompt-v1"

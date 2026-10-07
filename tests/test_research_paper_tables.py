import re
from pathlib import Path

import pytest

from research.paper_tables import BLOCKS, MANUSCRIPT, apply_blocks, render_blocks
from research.run import verify_results

RESULTS = Path(__file__).resolve().parents[1] / "research" / "results"


def _committed_runs():
    return sorted(p for p in RESULTS.iterdir() if (p / "manifest.json").exists()) if RESULTS.exists() else []


@pytest.mark.parametrize("run_dir", _committed_runs(), ids=lambda p: p.name)
def test_committed_results_are_unmodified(run_dir):
    assert verify_results(run_dir) == []


def test_manuscript_tables_match_committed_experiment_outputs():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    sources = set(re.findall(r"_Source: `(research/results/[^`]+)`", text))
    assert sources, "manuscript has no generated tables"
    root = MANUSCRIPT.parent.parent
    for rel in sources:
        tag, blocks = render_blocks(root / rel)
        assert apply_blocks(text, tag, blocks) == text, f"manuscript tables drifted from {rel}"


def test_apply_blocks_requires_markers():
    with pytest.raises(SystemExit):
        apply_blocks("no markers here", "smoke", {"primary": "x"})
    text = "a\n<!-- BEGIN GENERATED:smoke-primary -->\nold\n<!-- END GENERATED:smoke-primary -->\nb"
    assert "new" in apply_blocks(text, "smoke", {"primary": "new"})
    assert set(BLOCKS) == {"primary", "operational", "comparisons", "ablation", "errors"}

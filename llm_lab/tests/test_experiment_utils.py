from pathlib import Path

from llm_lab.benchmark.compare_runs import compare
from llm_lab.data.manifest import build_manifest


def test_manifest_hashes_dataset(tmp_path: Path):
    f = tmp_path / "finance.txt"
    f.write_text("revenue grew 10%", encoding="utf-8")
    m = build_manifest([str(f)], "finance-v1", "synthetic test data")
    assert m["dataset_name"] == "finance-v1"
    assert len(m["files"][0]["sha256"]) == 64
    assert m["files"][0]["bytes"] > 0


def test_benchmark_gate_passes_small_change():
    base = {"latency_p50_ms": 100, "tokens_per_second": 50}
    cand = {"latency_p50_ms": 105, "tokens_per_second": 48}
    assert compare(base, cand, 0.10, 0.90) == []


def test_benchmark_gate_detects_regression():
    base = {"latency_p50_ms": 100, "tokens_per_second": 50}
    cand = {"latency_p50_ms": 130, "tokens_per_second": 40}
    failures = compare(base, cand, 0.10, 0.90)
    assert len(failures) == 2

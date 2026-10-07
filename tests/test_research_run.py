import json
from pathlib import Path

import httpx
import pytest
import yaml

from research.dataset import load_manifest
from research.run import ARTIFACTS, ResultsExistError, run_experiment, verify_results

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "research" / "config" / "smoke.yaml"
SECRET = "sk-test-SECRET-never-written-42"


@pytest.fixture(scope="module")
def smoke_dir(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("OPENAI_API_KEY", SECRET)
    out = run_experiment(SMOKE, experiment_id="smoke-test", results_root=tmp_path_factory.mktemp("results"))
    mp.undo()
    return out


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_smoke_writes_all_artifacts_and_manifest(smoke_dir):
    for name in (*ARTIFACTS, "manifest.json"):
        assert (smoke_dir / name).exists(), name
    manifest = json.loads((smoke_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["dataset"]["dataset_sha256"] == load_manifest()["dataset_sha256"]
    assert manifest["dataset"]["holdout_used"] is False
    assert len(manifest["dataset"]["case_ids"]) == 40
    assert manifest["judge"]["is_llm"] is False
    assert "NOT an LLM" in manifest["evidence_label"]
    for key in ("git", "seed", "retrieval", "routing_policy", "runtime", "command", "config_sha256"):
        assert key in manifest
    assert manifest["judge"]["prompt_version"] == "judge-v1"


def test_smoke_predictions_cover_every_system_and_case(smoke_dir):
    preds = _read_jsonl(smoke_dir / "predictions.jsonl")
    config = yaml.safe_load(SMOKE.read_text(encoding="utf-8"))
    assert len(preds) == 40 * len(config["systems"])
    metrics = json.loads((smoke_dir / "metrics.json").read_text(encoding="utf-8"))
    assert set(metrics["systems"]) == set(config["systems"])
    b1 = metrics["systems"]["B1_deterministic"]
    assert b1["judge_human_agreement"]["value"] is None
    assert b1["automated"]["n"] == 40


def test_disagreements_have_required_fields(smoke_dir):
    rows = _read_jsonl(smoke_dir / "disagreements.jsonl")
    preds = _read_jsonl(smoke_dir / "predictions.jsonl")
    assert len(rows) == sum(1 for p in preds if not p["correct"])
    for row in rows:
        for key in ("case_id", "human_label", "judge_label", "confidence", "failure_category",
                    "retrieved_evidence", "reason_for_disagreement"):
            assert key in row


def test_results_are_immutable_and_tamper_evident(smoke_dir, tmp_path):
    assert verify_results(smoke_dir) == []
    with pytest.raises(ResultsExistError):
        run_experiment(SMOKE, experiment_id="smoke-test", results_root=smoke_dir.parent)
    copy = tmp_path / "copy"
    copy.mkdir()
    for f in smoke_dir.iterdir():
        (copy / f.name).write_bytes(f.read_bytes())
    (copy / "predictions.jsonl").write_bytes(b"{}\n")
    assert verify_results(copy) == ["modified predictions.jsonl"]


def test_no_secret_is_written(smoke_dir):
    for f in smoke_dir.iterdir():
        assert SECRET not in f.read_text(encoding="utf-8")


def test_holdout_requires_flag(tmp_path):
    with pytest.raises(PermissionError):
        run_experiment(SMOKE, splits=["holdout"], results_root=tmp_path)


def test_bootstrap_results_reproducible_across_runs(smoke_dir, tmp_path):
    again = run_experiment(SMOKE, experiment_id="smoke-again", results_root=tmp_path)
    a = json.loads((smoke_dir / "confidence_intervals.json").read_text(encoding="utf-8"))
    b = json.loads((again / "confidence_intervals.json").read_text(encoding="utf-8"))
    assert a == b


def test_llm_path_with_mocked_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    config = yaml.safe_load((ROOT / "research" / "config" / "default.yaml").read_text(encoding="utf-8"))
    config["experiment"]["name"] = "mock-llm"
    config["experiment"]["splits"] = ["dev"]
    config["systems"] = ["B2_single_judge", "B3_grounded_judge", "B4_hybrid", "A1_minus_rules"]
    config["bootstrap"]["iterations"] = 200
    path = tmp_path / "mock.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    calls = []

    def handler(request):
        calls.append(request)
        content = json.dumps({"verdict": "pass", "failure_category": "none", "confidence": 0.9,
                              "reason": "mock", "claims": []})
        return httpx.Response(200, json={"model": "gpt-4o-mini-mock", "choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 500, "completion_tokens": 50}})

    out = run_experiment(path, experiment_id="mock-llm", results_root=tmp_path / "r",
                         transport=httpx.MockTransport(handler))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["judge"]["is_llm"] is True
    assert manifest["judge"]["model_versions_reported_by_provider"] == ["gpt-4o-mini-mock"]
    # A1 (no rules) sends the same prompt as B3, so it must hit the cache rather than call again.
    assert manifest["judge"]["calls_made"] == len(calls) == 60
    assert manifest["judge"]["cache_hits"] == 20
    assert manifest["judge"]["estimated_spend_usd"] > 0
    for f in out.iterdir():
        assert SECRET not in f.read_text(encoding="utf-8")

from llm_lab.quantization.compare_quality import compare as compare_quant
from llm_lab.registry.model_card import render
from llm_lab.registry.model_registry import can_promote


def test_promotion_requires_evidence():
    record = {
        "dataset_manifest": "artifacts/data.json",
        "metrics": {"perplexity": 12.0, "tokens_per_second": 80.0},
    }
    ok, failures = can_promote(record, max_perplexity=15.0, min_tokens_per_second=50.0)
    assert ok
    assert failures == []


def test_promotion_blocks_missing_manifest():
    record = {"dataset_manifest": "", "metrics": {"perplexity": 10.0}}
    ok, failures = can_promote(record, max_perplexity=12.0, min_tokens_per_second=None)
    assert not ok
    assert "dataset manifest missing" in failures


def test_quantization_quality_gate():
    assert compare_quant({"perplexity": 10}, {"perplexity": 10.4}, 1.05) == []
    failures = compare_quant({"perplexity": 10}, {"perplexity": 11}, 1.05)
    assert failures


def test_model_card_contains_evidence():
    text = render({
        "name": "finance-llm-candidate",
        "stage": "candidate",
        "base_model": "example/base",
        "checkpoint": "ckpt/42",
        "dataset_manifest": "artifacts/data.json",
        "metrics": {"perplexity": 9.5, "tokens_per_second": 100},
        "quantization": "int4",
        "notes": "research only",
    })
    assert "finance-llm-candidate" in text
    assert "perplexity" in text
    assert "int4" in text

"""Perplexity evaluation for causal language models.

Designed for checkpoint-to-checkpoint comparisons after continued pretraining,
SFT, or quantization. Reports token-weighted NLL and perplexity.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def evaluate(model_name: str, text_path: str, max_length: int = 1024, stride: int = 512) -> dict:
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype="auto",
        device_map="auto",
    )
    model.eval()
    text = Path(text_path).read_text(encoding="utf-8")
    ids = tokenizer(text, return_tensors="pt").input_ids
    seq_len = ids.size(1)
    total_nll = 0.0
    total_tokens = 0

    with torch.inference_mode():
        for begin in range(0, seq_len, stride):
            end = min(begin + max_length, seq_len)
            trg_len = end - begin if begin == 0 else min(stride, end - begin)
            chunk = ids[:, begin:end].to(model.device)
            labels = chunk.clone()
            if trg_len < chunk.size(1):
                labels[:, :-trg_len] = -100
            out = model(chunk, labels=labels)
            predicted = max(trg_len - 1, 1)
            total_nll += out.loss.item() * predicted
            total_tokens += predicted
            if end == seq_len:
                break

    mean_nll = total_nll / max(total_tokens, 1)
    return {
        "model": model_name,
        "dataset": text_path,
        "tokens_scored": total_tokens,
        "mean_nll": mean_nll,
        "perplexity": math.exp(mean_nll),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--output", default="artifacts/perplexity.json")
    p.add_argument("--max-length", type=int, default=1024)
    p.add_argument("--stride", type=int, default=512)
    args = p.parse_args()
    result = evaluate(args.model, args.text, args.max_length, args.stride)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

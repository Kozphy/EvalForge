"""Compare baseline and quantized-model evaluation outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare(base: dict, quantized: dict, max_perplexity_ratio: float = 1.05) -> list[str]:
    failures: list[str] = []
    bp = float(base["perplexity"])
    qp = float(quantized["perplexity"])
    if qp > bp * max_perplexity_ratio:
        failures.append(
            f"quantization quality regression: perplexity {qp:.4f} > allowed {bp * max_perplexity_ratio:.4f}"
        )
    return failures


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", required=True)
    p.add_argument("--quantized", required=True)
    p.add_argument("--max-perplexity-ratio", type=float, default=1.05)
    args = p.parse_args()
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    quantized = json.loads(Path(args.quantized).read_text(encoding="utf-8"))
    failures = compare(base, quantized, args.max_perplexity_ratio)
    if failures:
        raise SystemExit("\n".join(failures))
    print("quantization quality gate: PASS")


if __name__ == "__main__":
    main()

"""Compare serving benchmark JSON and fail when a candidate regresses beyond policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare(base: dict, candidate: dict, max_latency_regression: float, min_throughput_ratio: float) -> list[str]:
    failures: list[str] = []
    base_latency = float(base["latency_p50_ms"])
    cand_latency = float(candidate["latency_p50_ms"])
    base_tps = float(base["tokens_per_second"])
    cand_tps = float(candidate["tokens_per_second"])
    if cand_latency > base_latency * (1 + max_latency_regression):
        failures.append(f"p50 latency regressed: {cand_latency:.2f}ms vs {base_latency:.2f}ms")
    if cand_tps < base_tps * min_throughput_ratio:
        failures.append(f"throughput regressed: {cand_tps:.2f} vs {base_tps:.2f} tok/s")
    return failures


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--max-latency-regression", type=float, default=0.10)
    p.add_argument("--min-throughput-ratio", type=float, default=0.90)
    args = p.parse_args()
    base = json.loads(Path(args.baseline).read_text())
    cand = json.loads(Path(args.candidate).read_text())
    failures = compare(base, cand, args.max_latency_regression, args.min_throughput_ratio)
    if failures:
        raise SystemExit("\n".join(failures))
    print("benchmark gate: PASS")


if __name__ == "__main__":
    main()

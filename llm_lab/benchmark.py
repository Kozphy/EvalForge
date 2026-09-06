import argparse
import json
import statistics
import time
import httpx


def percentile(values, p):
    if not values:
        return 0.0
    xs = sorted(values)
    k = min(len(xs) - 1, max(0, int(round((len(xs) - 1) * p))))
    return xs[k]


def main():
    p = argparse.ArgumentParser(description="Latency/throughput benchmark for an OpenAI-like local endpoint")
    p.add_argument("--url", default="http://127.0.0.1:9000/generate")
    p.add_argument("--prompt", default="Summarize the drivers of free cash flow in one paragraph.")
    p.add_argument("--requests", type=int, default=20)
    p.add_argument("--max-tokens", type=int, default=128)
    args = p.parse_args()

    latencies = []
    chars = 0
    start = time.perf_counter()
    with httpx.Client(timeout=120.0) as client:
        for _ in range(args.requests):
            t0 = time.perf_counter()
            r = client.post(args.url, json={"prompt": args.prompt, "max_tokens": args.max_tokens, "temperature": 0.2})
            r.raise_for_status()
            body = r.json()
            latencies.append((time.perf_counter() - t0) * 1000)
            chars += len(body.get("text", ""))
    wall = time.perf_counter() - start
    report = {
        "requests": args.requests,
        "wall_seconds": wall,
        "requests_per_second": args.requests / wall,
        "mean_latency_ms": statistics.mean(latencies),
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "output_chars_per_second": chars / wall,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

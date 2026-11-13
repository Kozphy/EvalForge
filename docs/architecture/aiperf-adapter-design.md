# Future adapter: NVIDIA AIPerf inference benchmarking

**Status:** Design only. **No GPU measurements have been collected in this repository.**  
Any latency, throughput, or cost numbers elsewhere in EvalForge are **not** AIPerf results.

## Purpose

Extend the Agent Reliability Platform (`agent_reliability/interface_v1.py`) with an optional
evaluator that measures model serving characteristics using
[NVIDIA AIPerf](https://github.com/NVIDIA/aiperf) (or successor NVIDIA inference perf tools)
when a GPU-capable environment is available.

## Non-goals (this document)

- Claiming TensorRT / Triton / NIM performance without a measured run
- Bundling GPU drivers or proprietary NVIDIA containers into EvalForge CI
- Auto-approving merges based on unpublished benchmark figures

## Proposed contract extension (not implemented)

```text
interface_id: evalforge.ci_failure_bridge
interface_version: 1.x  (additive fields only; bump minor)
evaluator: aiperf_v1
inputs:
  - endpoint_url (local or approved staging; never production secrets in git)
  - model_id
  - concurrency / input_len / output_len profiles
outputs (measured only when GPU run succeeds):
  - throughput_tokens_per_s
  - latency_p50_ms / latency_p99_ms
  - error_rate
  - hardware_label (e.g. "NVIDIA L4", from the run environment — not guessed)
  - aiperf_version
  - run_artifact_sha256
gate mapping:
  - missing GPU / tool → decision stays local-test-only; aiperf section = null
  - measured regression vs pinned baseline → WARN or BLOCK per policy pack
```

## Integration sketch

1. Keep AIPerf behind an optional extra (`pip install -e ".[aiperf]"`) — not a hard dependency.
2. Adapter implements the same `ReliabilityResponse` evidence envelope; `data_label` becomes
   `local_benchmark` only when a real AIPerf run completed.
3. CI on CPU runners **skips** the adapter and records `aiperf: NOT YET MEASURED`.
4. Peer mapping to ci-failure-orchestrator remains PASS→APPROVE, WARN→ESCALATE, BLOCK→REJECT.

## Verification bar before claiming results

| Requirement | Required evidence |
|---|---|
| GPU present | `nvidia-smi` output attached to evidence (redact hostnames if needed) |
| Tool version | `aiperf --version` (or equivalent) in the artifact |
| Reproducible command | Exact argv + profile YAML hashed into the evidence bundle |
| No secret leakage | Endpoint tokens redacted via `agent_reliability.redaction` |

Until those exist, documentation and dashboards must print **NOT YET MEASURED**, never zeros
or invented GPU metrics.

"""Generate a concise model card from a registered experiment record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(record: dict) -> str:
    metrics = record.get("metrics", {})
    lines = [
        f"# {record['name']}",
        "",
        f"**Stage:** {record.get('stage', 'unknown')}",
        f"**Base model:** {record.get('base_model', 'unknown')}",
        f"**Checkpoint:** `{record.get('checkpoint', '')}`",
        f"**Dataset manifest:** `{record.get('dataset_manifest', '')}`",
        f"**Quantization:** {record.get('quantization') or 'none'}",
        "",
        "## Evaluation",
        "",
    ]
    for key in sorted(metrics):
        lines.append(f"- **{key}:** {metrics[key]}")
    lines += [
        "",
        "## Intended use",
        "",
        "Research and engineering evaluation. Validate against task-specific benchmarks before deployment.",
        "",
        "## Limitations",
        "",
        "Metrics are only meaningful for the recorded datasets, prompts, hardware, and serving configuration. This card does not imply production fitness.",
        "",
        "## Notes",
        "",
        record.get("notes", ""),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--record", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(record), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()

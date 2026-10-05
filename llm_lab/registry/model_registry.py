"""Lightweight checkpoint registry with evidence-backed promotion gates."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ModelRecord:
    name: str
    stage: str
    base_model: str
    checkpoint: str
    dataset_manifest: str
    metrics: dict
    quantization: str | None = None
    notes: str = ""
    created_at: str = ""

    def normalized(self) -> dict:
        payload = asdict(self)
        payload["created_at"] = self.created_at or datetime.now(timezone.utc).isoformat()
        return payload


def can_promote(record: dict, max_perplexity: float | None, min_tokens_per_second: float | None) -> tuple[bool, list[str]]:
    failures: list[str] = []
    metrics = record.get("metrics", {})
    if max_perplexity is not None:
        ppl = metrics.get("perplexity")
        if ppl is None or float(ppl) > max_perplexity:
            failures.append(f"perplexity gate failed: {ppl}")
    if min_tokens_per_second is not None:
        tps = metrics.get("tokens_per_second")
        if tps is None or float(tps) < min_tokens_per_second:
            failures.append(f"throughput gate failed: {tps}")
    if not record.get("dataset_manifest"):
        failures.append("dataset manifest missing")
    return not failures, failures


def register(path: Path, record: ModelRecord) -> None:
    registry = []
    if path.exists():
        registry = json.loads(path.read_text(encoding="utf-8"))
    registry.append(record.normalized())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--record", required=True, help="JSON model record")
    p.add_argument("--registry", default="artifacts/model_registry.json")
    p.add_argument("--max-perplexity", type=float)
    p.add_argument("--min-tps", type=float)
    p.add_argument("--promote-stage", default="candidate")
    args = p.parse_args()

    raw = json.loads(Path(args.record).read_text(encoding="utf-8"))
    ok, failures = can_promote(raw, args.max_perplexity, args.min_tps)
    if not ok:
        raise SystemExit("\n".join(failures))
    raw["stage"] = args.promote_stage
    register(Path(args.registry), ModelRecord(**raw))
    print(f"registered {raw['name']} as {raw['stage']}")


if __name__ == "__main__":
    main()

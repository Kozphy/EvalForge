"""CLI: python -m agent_reliability [--evidence-dir DIR]."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability.interface_v1 import CandidateChange, ReliabilityRequest
from agent_reliability.pipeline import load_good_patch, run_local_reliability_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Agent Reliability fixture pipeline")
    parser.add_argument("--evidence-dir", type=Path, default=Path("agent_reliability/output"))
    parser.add_argument(
        "--scenario",
        choices=["good", "baseline_fail"],
        default="good",
        help="good=apply fixed calc.py; baseline_fail=no patch (expect BLOCK)",
    )
    args = parser.parse_args(argv)

    patch = load_good_patch() if args.scenario == "good" else ""
    req = ReliabilityRequest(
        candidate=CandidateChange(
            change_id=f"fixture-{args.scenario}",
            summary=f"local fixture scenario={args.scenario}",
            files_touched=["demo_pkg/calc.py"],
            patch_text=patch,
            request_merge=False,
            request_deploy=False,
        )
    )
    result = run_local_reliability_pipeline(req, evidence_dir=args.evidence_dir)
    print(
        json.dumps(
            {
                "decision": result.evidence.decision.value,
                "peer_outcome": result.evidence.peer_outcome,
                "run_id": result.evidence.run_id,
                "artifact_sha256": result.evidence.artifact_sha256,
                "allow_merge": result.evidence.policy.allow_merge,
                "allow_deploy": result.evidence.policy.allow_deploy,
                "data_label": result.evidence.data_label,
            },
            indent=2,
        )
    )
    return 0 if result.evidence.decision.value != "BLOCK" or args.scenario == "baseline_fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())

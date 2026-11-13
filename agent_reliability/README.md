# Agent Reliability Platform (EvalForge side)

Local-first bridge for coding-agent candidate changes:

```text
candidate → sandboxed pytest → regression assessment → PASS|WARN|BLOCK → redacted evidence
```

- **Interface:** `interface_v1.py` (`evalforge.ci_failure_bridge` / `1.0.0`)
- **Peer mapping:** PASS→APPROVE, WARN→ESCALATE, BLOCK→REJECT (ci-failure-orchestrator vocabulary)
- **Defaults:** `allow_merge=false`, `allow_deploy=false`, `production_ready_claim=false`
- **Data label:** synthetic / local fixture — not production evidence

```bash
python -m agent_reliability --scenario good
python -m agent_reliability --scenario baseline_fail
pytest -q tests/test_agent_reliability.py
```

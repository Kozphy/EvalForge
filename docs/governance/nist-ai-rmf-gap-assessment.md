# NIST AI RMF 1.0: evidence-based gap assessment (2026-11-11)

**Status:** Internal engineering self-assessment, **not** a NIST attestation, ISO/IEC 42001 certification, third-party audit, or production authorization.

**Scope:** `finance_eval/`, `app/controls.py`, local control-plane and operator demo, tests, and GitHub CI on the default branch reviewed for this PR. Assessment applies only to this repository and is **not** an organizational AI management-system assessment.

**Method:** Map selected NIST AI RMF 1.0 functions (GOVERN, MAP, MEASURE, MANAGE) to code paths and tests. Labels are `IMPLEMENTED (local evidence)`, `PARTIAL`, `GAP`. A path is a verification target, not proof that a particular CI run passed. No live provider or production access was used for this assessment.

| AI RMF function | Existing evidence / verification target | Status | Limit / next acceptance evidence |
| --- | --- | --- | --- |
| GOVERN — roles, accountability, oversight | `app/control_plane/`; `tests/test_operator_ui.py`; `docs/architecture/operator-ui-audit.md` | PARTIAL | Operator approval journey is fixture-backed; durable, independently attributable approvals and role permissions not established |
| GOVERN — policy and documentation | `finance_eval/policy.py`, `app/controls.py`, `tests/test_controls.py` | IMPLEMENTED (local evidence) | Illustrative thresholds, no documented business owner approval or independent validation |
| MAP — intended use / context | `README.md`, `docs/end-to-end-flow.md`, finance dataset manifest | PARTIAL | Finance/accounting sample is synthetic; no documented external stakeholder or deployment-context study |
| MAP — potential harms and affected parties | Finance failure taxonomy in `finance_eval/` | PARTIAL | Failure taxonomy exists; no full impact assessment, affected-person analysis or misuse evaluation |
| MEASURE — repeatable evaluation | `finance_eval/graders.py`, `finance_eval/runner.py`, `tests/test_finance_eval.py` | IMPLEMENTED (local evidence) | Offline author-generated fixtures; no independent real-model validation |
| MEASURE — regression, quality and thresholds | `finance_eval/policy.py`, `finance_eval/metrics.py`, `tests/test_regression.py` | PARTIAL | Metrics audit flags precision/recall/F1 defect; thresholds are illustrative, not externally justified |
| MEASURE — evidence integrity | `finance_eval/evidence.py`; **new** `finance_eval/verify_evidence.py` and `tests/test_verify_evidence.py` | PARTIAL | New read-only verifier checks byte hashes, not provenance, signatures, append-only enforcement or semantic correctness |
| MANAGE — risk response / release gate | `finance_eval/policy.py`, `app/controls.py`, `tests/test_controls.py` | IMPLEMENTED (local evidence) | Blocks synthetic candidates; no demonstrated enforcement at a real deployment boundary |
| MANAGE — monitoring / incident response | Operator UI prototype and local run records | GAP | No proven production telemetry, alert ownership, incident playbooks, or fleet metrics |
| MANAGE — documented exception handling | `app/control_plane/` and seeded review tests | PARTIAL | Prototype review state, no independently verifiable durable approvals or separation of duties |

## Prioritized backlog (acceptance-oriented)

- **P0 — evidence provenance and integrity.** Run read-only `verify_evidence` on each generated finance bundle before relying on its outputs; treat failures as blocking. Add signatures / trusted immutable storage if threat model requires protection against an actor who can rewrite both evidence and hashes.
- **P0 — fix metrics validity.** Correct `precision`, `recall`, `f1`, and `false_positive_rate` based on suitable independent ground truth or report `null` when unavailable; preserve historical outputs as historical.
- **P0 — enforce dataset provenance.** Validate pinned dataset file bytes before evaluation, rather than only validating after generation. Explicitly version any dataset correction (including known `PY-015` issue).
- **P1 — human oversight.** Persist approval decisions, actor identity, timestamps, policy snapshot and immutable review history; disallow self-approval; test authorization and bypass cases.
- **P1 — independent validation.** Use held-out, independently labelled real-model samples; report uncertainty and judge/human disagreement without seeded agreement claims.
- **P1 — operational governance.** Define deployment owner, intended use, rollback criteria, monitoring KPIs and incident management before any production authorization.

## Run the new verifier (read-only)

From repository root, after running the existing synthetic finance evaluation:

```bash
python -m finance_eval run --mode candidate
# Replace with a generated manifest path from your run:
python -m finance_eval.verify_evidence finance_eval/evidence/finrun_<run_id>.manifest.json
python -m pytest tests/test_verify_evidence.py -q
```

The manifest path is an **example shape**: actual evidence output directory depends on your run configuration. Use the concrete path printed or created by the runner. Verification returns exit code 0 only when the manifest's canonical payload hash, results bytes, dataset version, and dataset bytes match their pinned hashes. A successful check does **not** prove the underlying evidence is authentic, accurate, authorized or complete.

## Pre-existing findings and provenance

- `docs/end-to-end-flow.md`: documented repeatable local synthetic run; contains known metrics, hash enforcement and non-relocatable index concerns.
- `docs/architecture/operator-ui-audit.md`: control plane in-memory and approval prototype limitations.
- `README.md`: explicitly distinguishes local synthetic results from production or real-model validation.

**Review rule:** Only mark a control as operationally effective after a reviewer can inspect dated, independently reproducible test artifacts and evidence from the stated environment. This matrix is a scoped mapping of possible control evidence, not a compliance checklist signed off by NIST.

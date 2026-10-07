# External validation levels

| Level | Meaning | Status |
|---|---|---|
| **E0** | Internal synthetic benchmark; author-written cases and labels | **Achieved** (evalforge-bench v1.0.0) |
| E1 | Independent annotation: at least one annotator other than the author labels the benchmark; agreement reported | Not achieved |
| E2 | Public benchmark: results on an external dataset not written by the author (e.g. a public LLM-judge or groundedness benchmark) | Not achieved |
| E3 | Independent reproduction: someone other than the author reruns the experiment from the repo and reports results | Not achieved |
| E4 | Real-user or pilot evaluation: EvalForge used on real AI outputs by a real team, with consent | Not achieved |
| E5 | Production deployment evidence: sustained use in production with measured outcomes | Not achieved |

## What E0 supports

- Comparing evaluator designs on identical, frozen, hash-verified cases.
- Showing the pipeline mechanics: grounding, routing, audit artifacts, immutability.
- Showing measured behaviour of the deterministic baseline on these cases.

## What E0 does not support

- Claims about real-world error rates or production reliability.
- Claims that EvalForge is better than other evaluators "in general".
- Any statement about users, customers, reviewers, or incidents. **There are none.**

## Cheapest next steps

1. **E1:** have one independent person label the 80 cases blind to gold, then report Cohen's κ against the author labels.
2. **E2:** run the same B1-B4 harness on a public dataset with human labels.
3. **E3:** ask one person to run `python -m research.run --config research/config/smoke.yaml` from a fresh clone, and record the result in an issue.

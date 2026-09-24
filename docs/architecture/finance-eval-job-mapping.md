# Job Mapping — Finance Evaluation Portfolio

Mapped against repository evidence after `finance-accounting-v1` (154 cases).

## 1. Finance AI Trainer

| | |
|---|---|
| Evidence demonstrated | Versioned synthetic finance/accounting tasks with rubrics and failure modes |
| Remaining gap | No training/fine-tune loop, no preference data pipeline, no curriculum learning |
| Strongest artifact | `finance_eval/dataset/finance_accounting_v1.jsonl` |
| Interview talking point | “I design original finance tasks with structured goldens and known failure modes — training-ready labels, not scraped exams.” |

**Apply?** Only if the role values dataset design over training ops. Prefer Evaluator titles first.

## 2. Finance AI Evaluator

| | |
|---|---|
| Evidence demonstrated | 154-case benchmark, deterministic grading, FIN-* taxonomy, measured accuracy/regression, critical-error policy FAIL |
| Remaining gap | Multi-annotator IRR beyond seeded reviews; broader GAAP coverage; published live-model scorecards (keys local-only) |
| Strongest artifact | `docs/reports/finance-evaluation-report.md` + `finance_eval/` pipeline |
| Interview talking point | “I blocked a release when critical accounting error rate exceeded 5%, with hashed evidence and taxonomy-tagged failures.” |

**Apply?** **Yes — primary target.**

## 3. Coding Evaluator

| | |
|---|---|
| Evidence demonstrated | SQL/Python financial items graded on golden numeric results; instruction-following traps |
| Remaining gap | No sandboxed execution, no unit-test harness for arbitrary code, limited algorithmic breadth |
| Strongest artifact | `sql_financial` / `python_financial` categories + `GradeMode.SQL_RESULT` / `PYTHON_RESULT` |
| Interview talking point | “I evaluate finance code by result fixtures first — syntax-only checks are not enough for material errors.” |

**Apply?** Stretch / adjacent; strengthen with sandbox next.

## 4. LLM Evaluation Engineer

| | |
|---|---|
| Evidence demonstrated | Layered runner, metrics+CI, regression, policy, evidence manifests; plus EvalForge control plane |
| Remaining gap | Multi-provider live runners, durable stores, richer judge independence |
| Strongest artifact | `finance_eval/runner.py` + `tests/test_finance_eval.py` + existing CP tests |
| Interview talking point | “Deterministic graders are source of truth; judges are optional and labeled; every run emits hashed manifests.” |

**Apply?** **Yes.**

## 5. AI Governance Engineer

| | |
|---|---|
| Evidence demonstrated | Inspectable policy rules (PASS/WARN/FAIL/HUMAN_REVIEW_REQUIRED), audit evidence fields, human override disagreement tracking |
| Remaining gap | Durable append-only store, authZ, production incident evidence, model card automation |
| Strongest artifact | `finance_eval/policy.py` + evidence manifests + operator console governance story |
| Interview talking point | “Policy is code-reviewed and test-covered — critical finance errors cannot be waived by fluent LLM rationales.” |

**Apply?** **Yes as governance-minded evaluator**; full GRC title needs stronger ops evidence.

---

## Exact roles to apply for now

1. Finance AI Evaluator / Financial LLM Evaluator  
2. LLM Evaluation Engineer  
3. AI Evaluation Engineer (domain: finance)  
4. AI Governance / Evaluation Engineer (associate/mid — emphasize policy+evidence, not SOC2 ownership)  
5. Coding Evaluator — only with explicit honesty about fixture-based (not sandbox) grading

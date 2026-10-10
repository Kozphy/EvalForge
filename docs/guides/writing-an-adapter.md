# Writing an adapter

1. Implement `EvaluatorAdapter` (`healthcheck`, `prepare`, `execute`, `normalize`).
2. Register with `EvaluatorRegistry.register(adapter)`.
3. Never import your provider into orchestrator code.
4. Normalize into `EvaluationResult`.
5. Redact secrets before returning evidence.
6. Add a fake adapter for CI.

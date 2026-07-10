# EvalForge MVP

A local-first AI evaluation engineering platform for building repeatable benchmarks, grounding graders in approved evidence, checking deterministic requirements, measuring regressions, and routing uncertain cases to humans.

## What is included

- **Projects** for separating benchmarks and evidence collections.
- **Reference documents** stored locally and retrieved with TF-IDF RAG.
- **Evaluation cases** containing a prompt, candidate response, expected label, and deterministic requirements.
- **Deterministic graders** for sentence limits, word limits, required/forbidden phrases, and JSON validity.
- **Heuristic factuality grader** that works offline and deliberately routes weak evidence to review.
- **Optional OpenAI structured grader** using the Responses API and a Pydantic output schema.
- **Run history and metrics**, including accuracy, per-label precision/recall/F1, and a confusion matrix when expected labels are supplied.
- **Audit-friendly result records** containing evidence chunks, rule findings, claim verdicts, confidence, and human-review flags.
- **Minimal web UI**, REST API, SQLite persistence, Docker support, and tests.

## Architecture

```text
Evaluation cases
      │
      ├── deterministic rule checks
      │
      └── local retrieval over approved documents
                    │
                    ▼
       heuristic or structured LLM grader
                    │
                    ▼
 claims + evidence + severity + confidence
                    │
                    ▼
 metrics, regression history, human-review queue
```

The MVP keeps evidence local. The OpenAI provider sends the prompt, candidate response, configured rules, and retrieved evidence to the API only when explicitly selected.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
```

Activate the environment:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install and run:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

Create a project and select **Load sample data** to run the included accounting benchmark.

## Optional OpenAI grader

Copy the environment template and add an API key:

```bash
cp .env.example .env
```

Windows PowerShell equivalent:

```powershell
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY`, restart the service, and choose **OpenAI structured grader** in the UI. The adapter uses `client.responses.parse(...)` with the `GraderOutput` Pydantic schema.

OpenAI documentation used by this MVP:

- Responses API: https://platform.openai.com/docs/api-reference/responses
- Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The SQLite database is persisted in `./data`.

## Tests

```bash
pytest -q
```

## Example case payload

```json
{
  "name": "Land depreciation error",
  "prompt": "Explain depreciation in exactly two sentences.",
  "response": "Depreciation allocates an asset's cost over its useful life. Land is normally depreciated over an estimated useful life.",
  "expected_label": "major",
  "requirements": {
    "exact_sentences": 2,
    "max_words": null,
    "required_phrases": [],
    "forbidden_phrases": [],
    "require_json": false
  }
}
```

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET/POST | `/api/projects` | List or create projects |
| GET | `/api/projects/{id}` | Project, documents, cases, and runs |
| POST | `/api/projects/{id}/documents` | Add approved evidence |
| POST | `/api/projects/{id}/cases` | Add an evaluation case |
| POST | `/api/projects/{id}/cases/batch` | Add up to 10,000 cases in one request |
| POST | `/api/projects/{id}/seed` | Load sample benchmark |
| POST | `/api/projects/{id}/runs` | Execute a repeatable evaluation |
| GET | `/api/runs/{id}` | Retrieve metrics and detailed results |
| GET | `/docs` | Interactive OpenAPI documentation |

## Important limitations

This is an engineering MVP, not a production truth engine.

1. TF-IDF retrieval is intentionally simple. Replace it with embeddings or a managed vector store for larger corpora.
2. The offline heuristic uses lexical signals and cannot reliably determine real-world truth.
3. An LLM grader can also make mistakes. Calibrate it against human-labeled gold data.
4. No authentication, tenant isolation, background job queue, or rate limiting is included.
5. The current run endpoint is synchronous; production workloads should use a worker queue.
6. Never upload confidential material or assessment content whose rules prohibit external tools.

## Sensible next milestones

- JSONL/CSV upload UI and downloadable run reports
- Reviewer adjudication screen and inter-annotator agreement
- Prompt/model version registry
- Embedding-based retrieval and citation entailment checks
- Async workers, retries, cost/token tracking, and tracing
- RBAC, audit-log hashing, dataset versioning, and CI regression gates
- Text-to-SQL execution graders and domain-specific accounting controls

## License

MIT

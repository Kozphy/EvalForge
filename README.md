# EvalForge

Local-first AI evaluation engineering platform for building repeatable benchmarks, grounding graders in approved evidence, checking deterministic requirements, measuring regressions, and routing uncertain cases to humans.

**Current version: v0.2.0**

## v0.2 feature summary

- CSV and JSONL case import (dry-run, atomic, and partial modes)
- Evaluation report export (JSON / JSONL / CSV) with filters
- Expanded deterministic graders (words, sentences, regex, JSON Schema, citations, Python/SQL syntax, and more)
- Human-review queue with multi-reviewer decisions and adjudication
- Immutable per-run grader configuration snapshots (including Git SHA when available)
- Non-destructive SQLite schema upgrades and indexes

## What is included

- **Projects** for separating benchmarks and evidence collections
- **Reference documents** stored locally and retrieved with TF-IDF RAG
- **Evaluation cases** with prompts, candidate responses, expected labels, and requirements
- **Deterministic graders** that never call an LLM
- **Heuristic factuality grader** that works offline and routes weak evidence to review
- **Optional OpenAI structured grader** using the Responses API and a Pydantic output schema
- **Run history, metrics, exports, and human adjudication**
- Minimal web UI, REST API, SQLite persistence, Docker support, and tests

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
 metrics, exports, regression history, human-review queue
```

The platform keeps evidence local. The OpenAI provider sends the prompt, candidate response, configured rules, and retrieved evidence to the API only when explicitly selected.

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

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY`, restart the service, and choose **OpenAI structured grader** in the UI.

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

## JSONL import example

```bash
curl -X POST "http://localhost:8000/api/projects/1/cases/import" \
  -F "file=@examples/accounting_cases_v02.jsonl" \
  -F "dry_run=false" \
  -F "atomic=true"
```

Each JSONL row:

```json
{
  "case_id": "ACC-001",
  "name": "Land depreciation error",
  "prompt": "Explain depreciation in exactly two sentences.",
  "response": "Depreciation allocates an asset's cost over its useful life. Land is normally depreciated over an estimated useful life.",
  "expected_label": "major",
  "requirements": {
    "exact_sentences": 2,
    "max_words": null,
    "min_words": null,
    "required_phrases": [],
    "forbidden_phrases": [],
    "required_regex": [],
    "forbidden_regex": [],
    "require_json": false,
    "json_schema": null,
    "required_json_keys": [],
    "forbidden_json_keys": []
  },
  "metadata": {
    "domain": "accounting",
    "difficulty": "easy",
    "source": "IAS 16"
  }
}
```

`expected_label` accepts `pass`, `no_issue`, `minor`, or `major`. `pass` is normalized to `no_issue`.

## CSV import example

Nested `requirements` and `metadata` cells must be JSON-encoded strings. See `examples/accounting_cases.csv`.

```bash
curl -X POST "http://localhost:8000/api/projects/1/cases/import-csv" \
  -F "file=@examples/accounting_cases.csv" \
  -F "atomic=true"
```

Import limits (configurable via environment):

| Variable | Default |
|---|---|
| `EVAL_MAX_IMPORT_CASES` | `10000` |
| `EVAL_MAX_IMPORT_FILE_BYTES` | `20971520` (20 MB) |

Modes:

- **dry_run**: validate only
- **atomic=true**: write nothing if any row fails
- **atomic=false**: import valid rows and return errors for rejected rows

## Export examples

```bash
curl -L "http://localhost:8000/api/runs/1/export?format=json" -o run.json
curl -L "http://localhost:8000/api/runs/1/export?format=jsonl&review_required=true" -o review.jsonl
curl -L "http://localhost:8000/api/runs/1/export?format=csv&predicted_label=major" -o major.csv
curl -L "http://localhost:8000/api/runs/1/export?format=jsonl&incorrect_only=true" -o incorrect.jsonl
```

Exports include case content, labels, confidence, rule findings, evidence IDs, claim verdicts, reviewer decisions when present, and the run configuration snapshot.

## Human-review workflow

1. Run an evaluation. Low-confidence / unsupported claims set `needs_human_review`.
2. Open the review queue in the UI or call `GET /api/reviews`.
3. Inspect prompt, response, evidence, rule findings, and claim verdicts.
4. Submit reviewer decisions with `POST /api/reviews/{result_id}/decisions`.
5. If reviewers disagree, status becomes `DISAGREEMENT`.
6. An adjudicator sets the final label with `POST /api/reviews/{result_id}/adjudicate`.

Review states: `PENDING`, `REVIEWED`, `DISAGREEMENT`, `ADJUDICATED`.

## Grader configuration

Every run stores an immutable `config` snapshot (see `examples/grader_config.json`), including provider, model, prompt version, retrieval settings, rule-set version, dataset version, app version, and Git commit SHA when available. Historical runs remain interpretable after configuration changes.

## Database migration instructions

EvalForge uses SQLite with `CREATE TABLE IF NOT EXISTS` plus a non-destructive `migrate_schema()` step that adds missing columns and indexes on startup.

Upgrade steps:

1. Stop the server.
2. Back up `./data/evals.db` (and `-wal` / `-shm` if present).
3. Pull the new version and install dependencies.
4. Start the server. Schema upgrades apply automatically.
5. Do **not** delete the database unless you intentionally want a reset (`make clean`).

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET/POST | `/api/projects` | List or create projects |
| GET | `/api/projects/{id}` | Project detail |
| POST | `/api/projects/{id}/documents` | Add evidence |
| POST | `/api/projects/{id}/cases` | Add a case |
| POST | `/api/projects/{id}/cases/batch` | JSON batch create |
| POST | `/api/projects/{id}/cases/import` | CSV/JSONL import |
| POST | `/api/projects/{id}/cases/import-jsonl` | JSONL import |
| POST | `/api/projects/{id}/cases/import-csv` | CSV import |
| POST | `/api/projects/{id}/seed` | Load sample benchmark |
| POST | `/api/projects/{id}/runs` | Execute evaluation |
| GET | `/api/runs/{id}` | Run detail |
| GET | `/api/runs/{id}/export` | Download report |
| GET | `/api/reviews` | Review queue |
| GET | `/api/reviews/{result_id}` | Review detail |
| POST | `/api/reviews/{result_id}/decisions` | Submit decision |
| POST | `/api/reviews/{result_id}/adjudicate` | Final adjudication |
| GET | `/docs` | OpenAPI docs |

## Important limitations

EvalForge is an engineering platform, not a production truth engine.

1. Offline factuality remains heuristic. Lexical overlap is not real-world truth.
2. **Unsupported is not the same as false.** Missing evidence means review, not automatic contradiction.
3. LLM graders are not authoritative. Calibrate against human-labeled gold data.
4. Human adjudication is required for uncertain or high-risk decisions.
5. SQL syntax checks are conservative and do **not** execute SQL.
6. TF-IDF retrieval is intentionally simple.
7. No authentication, tenant isolation, background job queue, or rate limiting is included.
8. The run endpoint is synchronous.

## Security notes

- Never upload confidential material whose rules prohibit external tools when using the OpenAI grader.
- Import endpoints reject unsupported extensions, enforce size limits, sanitize filenames, and never execute uploaded content.
- Keep `OPENAI_API_KEY` in `.env`; do not commit secrets.

## Sensible next milestones

- Inter-annotator agreement metrics
- Embedding-based retrieval and citation entailment checks
- Async workers, retries, cost/token tracking, and tracing
- RBAC, audit-log hashing, dataset versioning, and CI regression gates

## License

MIT

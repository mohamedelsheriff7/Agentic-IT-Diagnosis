## Repository location

Run the setup, test, and Docker commands from `backend`.

```powershell
cd backend
```

# Workstream C — synthetic IT diagnosis backend

A complete FastAPI backend for a Python Diagnostic Agent and IBM watsonx Orchestrate. It exposes 17 deterministic tools, SQLite persistence, transactional worklogs/evidence, human review, mock notifications and safe resolution gates. It does not implement an agent, call an LLM, reset accounts, grant access, or send messages.

## Start on Windows PowerShell

The merged Workstream A profile is available in `data/workstream_a`: 500 historical tickets plus 134 new test tickets. See [the merge validation report](docs/workstream_a_merge_report.md) for repairs and outstanding team decisions. To load this profile, run `python -m scripts.import_data --data-dir data/workstream_a` from `backend/` with the configured admin command key. Start the API on port 8000 and test with `TST-0001`. The instructions below describe the original starter setup. Ground truth remains offline in `evaluation/workstream_a`.

Use Python 3.12 or later. Open PowerShell in this project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
# Edit .env: replace API_KEY and ADMIN_API_KEY with different random values.
# Example generator: [guid]::NewGuid().ToString('N')
$env:ADMIN_API_KEY = Read-Host 'Enter the admin key configured in .env'
$env:ADMIN_COMMAND_KEY = $env:ADMIN_API_KEY
.\.venv\Scripts\python.exe -m scripts.import_data
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API base URL is `http://127.0.0.1:8000`. Swagger is `http://127.0.0.1:8000/docs`; **/docs is not the API base URL**. Use Swagger Authorize with the service key for tools, or the separate admin key for review decisions. Missing keys fail closed. No fixtures are loaded on startup; tables are created if absent.

In another PowerShell window, from the project directory:

```powershell
$env:API_KEY = Read-Host 'Enter the service key configured in .env'
Invoke-RestMethod http://127.0.0.1:8000/tickets/INC-1001 -Headers @{ 'X-API-Key'=$env:API_KEY }
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.smoke
```

Smoke adds one synthetic ticket and observation. Run it on a fresh demo dataset because it checks the initial outage counts. Keep secrets in environment variables or ignored .env, never source control. Environment variables override .env values.

## Docker

Requires Docker Engine/Desktop with Compose. Configure .env as above:

```powershell
docker compose up --build -d
$env:ADMIN_COMMAND_KEY = Read-Host 'Enter the admin key configured in .env'
docker compose exec -e ADMIN_COMMAND_KEY=$env:ADMIN_COMMAND_KEY api python -m scripts.import_data
docker compose logs api
```

SQLite lives in the named `sqlite_data` volume and survives container restarts and `docker compose down`. Do not use `down -v` unless intentionally deleting it. Docker artifacts are provided; Docker was unavailable on the implementation host, so container build/run remains unverified. The service runs as a non-root container user. Evaluation files are excluded from the image.

## Fixtures, clock, reset and team data

Starter data: 40 resolved/closed historical tickets, 30 open tickets, 24 taxonomy diagnoses, 24 approved articles, seven groups, three outage clusters and three decoys. Six historical tickets (15%) have visible misrouting/reassignment logs. All people, assets, checks and services are synthetic.

`DEMO_CLOCK=2026-10-01T12:00:00Z` freezes service time. An empty DEMO_CLOCK uses real UTC. Fixture dates must match the selected clock; changing the API clock does not rewrite persisted dates.

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_fixtures --seed 42 --clock 2026-10-01T12:00:00Z
$env:ADMIN_COMMAND_KEY = $env:ADMIN_API_KEY
.\.venv\Scripts\python.exe -m scripts.import_data --validate-only
# Explicitly replace all operational data, reviews and retry records:
.\.venv\Scripts\python.exe -m scripts.import_data --reset --confirm RESET_SYNTHETIC_DEMO
```

Reset/import is an authenticated local administrative command, excluded from agent tools. It validates all files and references and replaces the database contents transactionally. Back up the SQLite database before replacing useful demo work. API workers should be stopped during administrative replacement. A reset intentionally discards old action IDs.

For Workstream A/B, copy the `data` directory to a staging directory and replace the relevant JSON files. Validate with `--data-dir PATH --validate-only`, then import with the same directory and explicit reset. JSON schemas are in `specs/dataset.schemas.json`; semantic/FK validation is in `app/importer.py`. The import test loads 500 historical and 90 open tickets. Workstream A must independently author the final 400–600 historical and 80–100 evaluation cases; these generated starter records do not substitute for that work. Workstream B can replace the versioned article JSON while preserving the schema. Keep expected answers in `evaluation`, never in operational ticket fields.

## Orchestrate

Supply a tenant-reachable HTTPS endpoint via your deployment/reverse proxy. No tunnel or public deployment is created by this project. Never use localhost in the tenant export. The checked-in example server `https://workstream-c.example.com` is reserved documentation data and is **not deployed**.

```powershell
$env:PUBLIC_BASE_URL = 'https://your-real-service.example.org'
.\.venv\Scripts\python.exe -m scripts.export_openapi
.\.venv\Scripts\python.exe -m scripts.validate_openapi
```

Import `specs/agent.openapi.yaml` (or equivalent JSON) and bind `specs/connection.yaml`. Follow [the ADK/UI guide](docs/orchestrate_setup.md). Re-export the specification and connection whenever the public endpoint changes. `specs/developer.openapi.json` is the full developer contract, including health and admin routes; do not import it as the agent tool set.

## Project guide

- `app`: schemas, SQLAlchemy tables, API routes, policies, repositories, retrieval, transactional services and importer.
- `scripts`: explicit fixture generation/import, OpenAPI export/validation and real HTTP smoke.
- `data`: operational starter fixtures; `evaluation`: private scenario answers/ground truth, never served or loaded.
- `tests`: workflow, negative-policy, transaction, persistence, import and OpenAPI checks.
- [Integration contract](docs/integration_contract.md), [tool catalog](docs/tool_catalog.md), [four demo flows](docs/sample_scenarios.md), [ticket schema](docs/ticket_schema.md), [Maximo concept mapping](docs/maximo_field_mapping.md), [assumptions](docs/assumptions.md), [verification report](docs/test_report.md).

The backend verifies IDs, recorded observations, article conditions and policy consistency. It cannot independently verify an agent's reasoning, user assertions, or arbitrary security-sensitive text. Explicit safety flags are preserved conservatively. SQLite and shared demo keys suit a prototype, not a production multi-tenant deployment.

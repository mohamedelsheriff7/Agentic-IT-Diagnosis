# IT Diagnostic Agent — standalone implementation

## Native LangGraph agent

For direct WXO agent import, use `dist/isys-diagnostic-langgraph-v6.8.1.zip` and the [native LangGraph import guide](docs/NATIVE_LANGGRAPH_IMPORT.md). The package returns an uncompiled StateGraph for the platform to host. The same factory runs locally at `POST /langgraph/chat`. Replies are conversational; the separate [versioned result contract](docs/DIAGNOSTIC_RESULT_CONTRACT.md) is exposed at graph output `diagnostic_result`, in message metadata and through HTTP.

The v6.8 backend-connected path now supports KB-001 guided resolution with exact step tracking, separate success confirmation and backend-confirmed RESOLVED. See the [delivery status and remaining gaps](docs/V68_RUNTIME_PATCH.md) before treating this prototype as ready.

KB-001 display guidance is updated in v6.8.1; see [the scoped patch note](docs/V681_KB001_GUIDANCE.md). Other reported fixes remain deferred.

## Current HTTP service

The project now includes a localhost API, authenticated investigation tools, persistent multi-turn sessions, and a separate `diagnostic-agent.openapi.json` export. Run `.\Start-Agent.ps1` and open http://127.0.0.1:8080/docs. Configuration, current limitations, knowledge approval status, and Orchestrate import steps are in [Local API and Orchestrate](docs/LOCAL_API_AND_ORCHESTRATE.md). The older standalone notes below describe the original facade; backend hosting is now implemented separately in `server.py`.

The sections below describe the original standalone facade. Native LangGraph and the backend-connected graph are the current delivery path; the original facade remains available for offline experiments.

## Included

- Existing deterministic diagnostic engine, knowledge retrieval, historical-ticket similarity, evidence tracking, and question selection.
- Combined system prompt: shared safety instructions + Diagnostic Agent role instructions.
- Optional OpenAI-compatible Chat Completions client for LLM-assisted question planning.
- JSON session persistence per ticket, independent of the current working directory.
- Standalone CLI and a structured result wrapper.
- Offline tests for prompt composition, secret redaction, state persistence, action validation, and mandatory priority-1 escalation.

## Standalone facade boundaries

- The LLM proposes questions and candidate hypotheses. It cannot run tools, create evidence, approve articles, assign tickets, escalate, or resolve tickets.
- The standalone facade does not call backend tools or write backend worklogs. Select backend mode in the HTTP service to use the integration.
- A local result uses `integration_status: LOCAL_ONLY_BACKEND_NOT_CONNECTED`; `completed_actions` remains empty.
- The JSON session store is for local prototype/testing only. It is not a replacement for a shared production database.
- Only explicitly approved articles are retrieved for the normal diagnostic knowledge path. Drafts must not authorize resolution.
- The current heuristic engine is a baseline. Confidence is exposed categorically with its basis and caveats, not as a probability.

## Setup

Use Python 3.12 for the validated native/API environment. Core-only experiments use the standard library; native/API dependencies are pinned in `requirements.txt`.

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt pytest httpx
pytest -q
```

The existing `pyproject.toml` configures `adk-project/agents` on the test import path.

## Run locally

Create `ticket.json`:

```json
{
  "ticket_id": "INC-TEST-001",
  "summary": "Cannot access Portal",
  "description": "I can sign in to email but Portal says I do not have access.",
  "priority": "3",
  "ticket_class": "INCIDENT",
  "security_sensitive": false,
  "privileged_access": false,
  "configuration_item_id": "CI-PORTAL",
  "location_id": "LOC-A"
}
```

Start or resume a local session:

```bash
PYTHONPATH=adk-project/agents python -m diagnostic_agent --ticket-json ticket.json
```

Submit the answer to the saved next question (use a unique evidence ID for each answer):

```bash
PYTHONPATH=adk-project/agents python -m diagnostic_agent --ticket-json ticket.json --answer "Yes, email works" --evidence-id USER-ANSWER-001
```

Session files are written under `data/sessions/` by default. Keep this directory private; use only synthetic project records.

## Enable LLM-assisted question planning

1. Copy `.env.example` values into your shell environment (do not commit credentials).
2. Set `DIAGNOSTIC_LLM_BASE_URL`, `DIAGNOSTIC_LLM_API_KEY`, and `DIAGNOSTIC_LLM_MODEL` for a provider that implements the OpenAI-compatible `/chat/completions` endpoint and JSON response mode.
3. Run:

```bash
PYTHONPATH=adk-project/agents python -m diagnostic_agent --ticket-json ticket.json --use-llm
```

No API key is bundled. If the provider is unconfigured/unavailable, the agent falls back to deterministic question selection. Provider compatibility must be verified against the actual service before deployment.

## System prompt

- `adk-project/agents/diagnostic_agent/prompts/shared_instructions.md`
- `adk-project/agents/diagnostic_agent/prompts/diagnostic_agent_role.md`

The runtime concatenates the shared block first, then the role instructions. Keep these instructions aligned with the approved policy and backend schemas.

## Current output meanings

- `ASK_MORE`: ask the returned question and return control to the user/Supervisor.
- `ROUTE`: recommendation only; assignment is not executed locally.
- `ESCALATE`: recommendation/mandatory human requirement; no escalation is claimed completed locally.
- `RESOLVE`: must never be taken from an LLM proposal alone. The current local facade does not resolve tickets.
- `outcome=INCONCLUSIVE` means no defensible diagnosis has been established; `HUMAN_REQUIRED` means human handling is required.

## Deferred backend integration checklist

Implement adapters for `get_ticket_details`, `search_diagnostic_knowledge`, `search_similar_tickets`, `check_account_status`, `check_application_entitlement`, `check_service_health`, `add_worklog_entry`, `record_diagnostic_result`, and `resolve_ticket`. Then map local evidence IDs to backend-returned IDs, persist the exact backend result ID/version, and enforce policy gates in the backend as well as the agent. Finally expose a supported `external_chat` or A2A interface and register it with the Supervisor in watsonx Orchestrate.

## Connect to the Workstream C backend

The project now includes an HTTP adapter for all 17 exported Workstream C tools and a conservative integrated investigation CLI. The adapter follows `agent.openapi.json`'s `X-API-Key` header authentication and paths. It uses only the Python standard library; no HTTP dependency is required.

1. Copy `.env.example` to `.env` for your own reference, then export the backend values in your terminal. The application does **not** automatically load `.env` files.

```bash
export DIAGNOSTIC_BACKEND_BASE_URL="https://your-backend-host.example"
export DIAGNOSTIC_BACKEND_API_KEY="YOUR_SERVICE_API_KEY"
```

2. From the project root, run an existing backend ticket:

```bash
PYTHONPATH=adk-project/agents python -m diagnostic_agent.integrated --ticket-id TST-0001
```

You can override the base URL with `--base-url`. Keep the API key in the environment; do not paste it into source code, command history, tickets, or Git.

### What the integrated workflow does

- Fetches the latest ticket details before investigating.
- Searches approved diagnostic knowledge and similar historical tickets.
- Runs applicable account, entitlement, and/or service-health checks when the ticket contains the required identifiers and relevant symptom clues.
- Gives priority-1, security-sensitive, and privileged-access cases a mandatory human-review path.
- Records a conservative diagnostic result and worklog for active tickets when backend validation accepts them.
- Refuses to mutate tickets already marked RESOLVED or CLOSED.

### Deliberate safety boundary

This is a connected initial-investigation workflow, **not an autonomous resolver**. It currently records `INCONCLUSIVE` / `ASK_MORE` for ordinary tickets, because article approval, exact condition satisfaction, user success confirmation, and the latest diagnostic-result match must all be proven before resolution. It does not automatically assign a specialist, create/link a global incident, notify resolver groups, or resolve a ticket. Those methods are available in the backend adapter for controlled tests, but the investigation workflow does not invoke them. Backend fixture checks are not live account or monitoring integrations. A human-review request is a request, not approval.

The CLI prints structured JSON including each backend action that succeeded or failed. HTTP/API validation errors are surfaced without printing the API key. Test against synthetic tickets first.

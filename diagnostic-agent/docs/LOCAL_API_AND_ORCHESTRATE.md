# Local service and Orchestrate tools

Use the outer project at `IT-Diagnosis-Agent-final/IT-Diagnosis-Agent-final`, not its nested `IT-Diagnosis-Agent-review` copy. Python 3.12 is tested.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env # only on first setup; preserve existing keys
# Edit .env and set DIAGNOSTIC_SERVICE_API_KEY to a random secret.
.\Start-Agent.ps1
```

Open http://127.0.0.1:8080/docs. Click Authorize and enter the **agent service key** from `.env`. This is separate from the backend service key. Both are server-side settings; never put keys in the OpenAPI document. Restart after changing `.env`.

`GET /health` reports whether backend and optional LLM credentials are configured; it does not prove remote connectivity. The root page links to Swagger. This is an API service, not a conversational web UI.

Start a local investigation with `POST /investigations`:

```json
{"mode":"local","ticket_id":"DEMO-001","ticket":{"ticket_id":"DEMO-001","summary":"Cannot access Portal","description":"Email works but Portal says access denied","priority":"3"}}
```

Answer its outstanding question with `POST /investigations/DEMO-001/answers`:

```json
{"mode":"local","answer":"Yes","evidence_id":"ANSWER-001"}
```

Use a new evidence ID for each new answer. `GET /investigations/DEMO-001?mode=local` returns the saved evidence and trace. Repeating start resumes existing state. Local and backend sessions live in separate directories. Local mode performs no backend actions and cannot close tickets.

For backend mode, set `DIAGNOSTIC_BACKEND_API_KEY` and use an existing synthetic ticket ID:

```json
{"mode":"backend","ticket_id":"TST-0001"}
```

Use `mode=backend` in subsequent answer requests and trace retrieval. Backend investigation writes audit worklogs and diagnostic results and may request human review. Existing-global links and new-global creation are proposals for Supervisor/human review under the pending policy. It recommends routing to the Supervisor; it does not implement the other collaborator agents. Explicit resolution confirmation is backend-only and requires all exact article step IDs, verified resolution conditions, and user confirmation. Unstructured article human restrictions conservatively require human review. Backend validation remains authoritative. Failures return HTTP errors; rejected closures never become successful resolutions.

## Knowledge and instructions

The provided updated knowledge JSON is copied to `adk-project/knowledge/reviewed`. Its approval register is pending and its articles retain `approved=false`. The generated `.env` selects this snapshot. The legacy bundled knowledge contains different approval flags and is retained for compatibility with existing tests; it is not selected by this service. Do not mark articles approved merely to make the demo pass. Authoritative review/approval and backend article versions must be aligned before testing automatic resolution.

Existing prompts are `adk-project/agents/diagnostic_agent/prompts/shared_instructions.md` and `diagnostic_agent_role.md`. Paste proposed instructions in the chat for review before replacing these files. Prompts affect optional LLM question planning only; deterministic safety and backend policy checks remain in Python. Set all three `DIAGNOSTIC_LLM_*` variables and `use_llm=true` for local question planning. Backend mode currently uses the deterministic engine. Without LLM configuration the agent still runs locally.

## Publish later and export

Keep the API on port 8080 and expose it through your HTTPS hosting or tunnel. The backend's existing ngrok URL hosts Workstream C; the agent needs its own reachable URL. Localhost cannot be reached from an Orchestrate tenant.

```powershell
.\.venv\Scripts\python.exe serve.py --export-only --public-url https://YOUR-AGENT-HOST
```

This writes `diagnostic-agent.openapi.json`, an OpenAPI 3.0.3 specification with the agent URL and `X-API-Key` security. The existing `agent.openapi.json` is the **backend tool contract**, not this agent service. Use the new file.

In Orchestrate: add tools > import OpenAPI > upload `diagnostic-agent.openapi.json` > select the four investigation operations > bind an API-key connection using the agent service key in `X-API-Key`. In Supervisor instructions, tell it to start with backend mode, relay `next_question`, submit the answer for the same ticket, inspect the trace, and follow the recommended action. Never infer successful resolution from a recommendation.

OpenAPI imports the service as tools. Registering it as a true external collaborator requires an A2A or compatible chat-completions adapter; that protocol is not implemented here. IBM references:

- https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=building-tools
- https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=platforms-adding-agents-from-third-party

Run one server worker: the JSON store uses atomic writes and this process serializes transitions. Shared multi-instance deployment needs transactional database-backed sessions and stronger ownership/isolation controls.

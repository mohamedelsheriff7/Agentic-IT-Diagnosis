# Native LangGraph import

The current import artifact is `dist/isys-diagnostic-langgraph-v6.8.1.zip`, with agent name `isys_diagnostic_langgraph_v6_8_1`. It contains `agent.yaml`, a self-contained uncompiled `agent:create_agent` factory, and pinned dependencies. The entrypoint embeds the allowlisted diagnostic Python modules, synthetic historical context, and reviewed knowledge snapshot, extracting them into a temporary runtime directory before importing the core. It works when the entrypoint is relocated without sibling package folders. Secrets, virtual environments, operational databases, and evaluation answers are excluded.

The v1 ZIP is retained only to reproduce its `No module named 'diagnostic_agent'` failure under entrypoint-only loading. Import v6.8 and select the existing `isys_it_backend` connection. Test it in a new preview conversation before replacing the Supervisor's collaborator. The current package has been verified locally; this version has not been imported into your tenant during this verification.

## Import into WXO

1. In WXO Connections, create a **team** connection with app ID `isys_it_backend`, credential type `api_key`, and the Workstream C backend service key. Do not use the local agent-service key.
2. Open the agents page, select **Create agent > Import LangGraph agent**, and upload the ZIP.
3. Select the `isys_it_backend` connection during import. The factory reads the injected `isys_it_backend_api_key` credential. The backend base URL is currently `https://shelf-roman-swimmable.ngrok-free.dev`; change the factory default and rebuild if the backend URL changes.

The current package accepts the named credential during factory creation or graph invocation. A missing key reports the exact connection binding required. Your computer's `.env` is not uploaded: saving a key locally does not configure WXO. The connection **app ID** (not just its display name) must be `isys_it_backend`, its credential type must be `api_key`, and team credentials must be configured and selected for this imported agent.
4. Open the imported agent's preview and send a synthetic ticket ID, for example `TST-0001`. Subsequent messages answer the outstanding diagnostic question. Replies contain a short explanation and the next question or recommended action in plain language. A compact ticket/checkpoint receipt supports continuation if the host removes message metadata. You do not need to paste additional instructions in WXO.
5. Add `isys_diagnostic_langgraph_v6_8_1` as a collaborator to the Supervisor. It owns diagnosis; the Supervisor remains responsible for assignment and global-incident operations. Verify the Supervisor can consume `diagnostic_result` as described in [the result contract](DIAGNOSTIC_RESULT_CONTRACT.md).

There is no public agent URL to configure for native import: WXO hosts and compiles the graph. The backend URL must remain reachable from the WXO runtime. IBM documents native import for commercial IBM Cloud/AWS deployments; check your tenant's availability if the import option is absent.

## How the graph runs

In v4, contradictory current evidence reopens an excluded hypothesis instead of dropping either observation. A shared-service conflict returns an explicit Supervisor handoff and evidence references, with no confirmed diagnosis or autonomous global-ticket operation. Existing v3 diagnostic snapshots can be reconciled on resume; a new preview conversation is recommended for a clean comparison.

The factory returns an actual uncompiled `StateGraph`. Its nodes read the request, choose investigation/answer/explicit confirmation, execute the existing diagnostic engine and backend adapter, then emit a conversational assistant message. Full structured results remain available in `AIMessage.additional_kwargs["isys_diagnostic"]`. No Orchestrate OpenAPI tool is registered or called by the graph. Backend integration uses the packaged Python HTTP adapter. Native platform restrictions on packaged tools/side effects and outbound API access still require tenant validation; local backend success does not establish tenant compatibility.

Only messages are guaranteed to survive WXO turns. The agent stores its diagnostic snapshot in assistant-message metadata. It also writes a sanitized, compressed checkpoint using existing backend NOTE worklogs. If metadata is unavailable, it restores the checkpoint identified by the compact receipt in its previous visible reply. It reads legacy JSON replies too. Checkpoints use unique action IDs, indexed chunks, checksums, and bounded decoding; missing or corrupted checkpoints stop continuation safely. These notes add audit storage and backend calls per diagnostic turn. They are never TOOL_CHECK evidence and are not written to resolved/closed tickets. It does not depend on a shared process-global JSON directory. The YAML requests SQLite checkpoints; IBM states these survive turns but not pod replacement. Use the documented PostgreSQL checkpointer configuration for durable hosting across pod restarts.

This graph uses the deterministic diagnostic engine. The shared/role prompts are included; optional LLM question planning in the standalone facade remains separate. The reviewed bundle has 38 owner-approved local articles: 24 exact backend mirrors, two local diagnostic articles and 12 local guidance articles. Only backend KB-001 authorizes agent resolution. Local content approval does not register an article with the backend or activate outage policy.

## Local graph test

Start `.\Start-Agent.ps1` and open http://127.0.0.1:8080/docs. Authorize using `DIAGNOSTIC_SERVICE_API_KEY`, then call `POST /langgraph/chat`. The local host compiles the same factory with a SQLite checkpointer. Reuse `session_id` on later turns. The HTTP response keeps structured fields for integrations and includes the conversational text in `reply`. In WXO, the assistant-message content is the conversational text itself. Factory option `response_format="structured"` is available for explicit debugging only.

First request:

```json
{"session_id":"demo-graph","mode":"backend","message":"Investigate TST-0001"}
```

Next request:

```json
{"session_id":"demo-graph","mode":"backend","message":"Unknown, error code 512"}
```

Use `mode=local` with a JSON-encoded synthetic ticket in `message` for offline testing. In backend mode, v6.8 supports conversational guided resolution: a scoped completion answer records the outstanding exact step ID, followed by a separate original-problem success question. Explicit success, the matching latest diagnostic result, all safety gates and backend success are required. An unsolicited success claim cannot skip those stages. Local mode performs no backend resolution.

Rebuild and validate:

```powershell
.\.venv\Scripts\python.exe scripts\build_langgraph_package.py
.\.venv\Scripts\python.exe scripts\verify_langgraph_package.py
```

## Official references

- [Package and factory contract](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=agents-creating-langgraph-package-import)
- [Native import procedure and limitations](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=agents-importing-langgraph)
- [Connection credential injection](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=agents-creating-connections-langgraph)
- [Checkpoint persistence](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=agents-enabling-state-persistence-langgraph)

## Version 5.1 answer interpretation

Natural observations for DNS, Wi-Fi, printer, synchronization and certificate questions are stored with the original USER_RESPONSE evidence IDs. Recognized facts can answer more than one question. Ambiguous either/or replies get one clarification; unknown answers remain unknown. Another working Wi-Fi device does not eliminate a device-specific connection problem. Each supported handoff names the observations, a tentative hypothesis, and the missing direct verification. User reports alone do not become TOOL_CHECK evidence or authorize resolution.

A fresh preview/import can resume the backend checkpoint matching the ticket's latest diagnostic result. Older unmapped answers are reinterpreted using their original question and evidence ID. Audit storage is not duplicated as new user answers.

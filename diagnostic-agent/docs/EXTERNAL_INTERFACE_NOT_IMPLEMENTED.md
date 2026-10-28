# Deferred: external-agent interface

The HTTP service is now implemented in `server.py` with an OpenAPI tool export. See [Local API and Orchestrate](LOCAL_API_AND_ORCHESTRATE.md). A true external-agent protocol remains deferred.

When integrating later, select based on the interface actually implemented:
- `external_chat` only when exposing a compatible Chat Completions interface.
- A2A only when implementing the supported A2A version expected by the target Orchestrate environment.
- A plain FastAPI JSON route is not automatically either protocol.

The eventual wrapper should validate input, call the standalone facade, return the structured result, and keep the backend tool adapters in a separate module. Do not let model output bypass backend policy gates.

# Orchestrate setup

Official documentation checked on 2026-10-01. Commands below are verified against documentation, not executed in a tenant.

## Export

Set PUBLIC_BASE_URL to the real HTTPS API root, then run `python -m scripts.export_openapi` and `python -m scripts.validate_openapi`. The exporter requires one non-parameterized HTTPS server, excludes health/admin endpoints and unused admin schemas, converts nullable unions/constant/enumeration and numeric-exclusive-bound constructs to OpenAPI 3.0.3, and validates it. Unsupported constructs fail export. The example.com host is an undeployed example; re-export before tenant testing.

IBM requires JSON operations, OpenAPI 3.0, a single server and operation IDs; operation IDs become tool names. This contract uses the 17 requested snake_case names. [IBM OpenAPI authoring](https://developer.watson-orchestrate.ibm.com/tools/create_openapi_tool).

## ADK

Install/configure IBM's ADK separately following its environment onboarding documentation and activate your intended tenant. Backend requirements deliberately do not install an agent framework. Authenticate the ADK with the **IBM Orchestrate key**. That key is different from this backend's **API_KEY**.

From this project directory, with the backend service key in the PowerShell environment:

```powershell
orchestrate connections import -f specs/connection.yaml
orchestrate connections set-credentials -a workstream_c --env draft --api-key $env:API_KEY
orchestrate connections set-credentials -a workstream_c --env live --api-key $env:API_KEY
orchestrate tools import -k openapi -f specs/agent.openapi.yaml -a workstream_c
orchestrate tools list -v
```

The generated connection uses `kind: api_key`, `type: team`, and `name: X-API-Key` in draft/live. It contains no secret. Set live credentials only where that environment is supported. The API key is a connection credential, never an agent argument. Never provide ADMIN_API_KEY to agents. [IBM connections and credential commands](https://developer.watson-orchestrate.ibm.com/connections/build_connections).

Reimporting the same operation names updates tools; after changing endpoint, re-export/reimport both files, update connection credentials as needed, and verify bindings. [IBM managing tools](https://developer.watson-orchestrate.ibm.com/tools/manage_tool).

## UI

In the applicable workspace, open Build → All tools → Create tool → OpenAPI. Alternatively open the intended agent and add an OpenAPI tool from its tool area. Upload agent.openapi.yaml or agent.openapi.json, review and select the 17 operations, then import. [IBM UI import guide](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=tools-importing-from-openapi).

Choose/create the API-key connection for the deployed backend, with header X-API-Key, and enter the backend service key through connection credential management. Bind the connection for tool usage and configure draft/live as needed; a tool import alone does not establish working credentials. [IBM connection binding](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=credentials-binding-deploying-connections).

## Tenant acceptance still required

1. Deploy behind valid TLS and confirm Orchestrate can reach the endpoint (including tenant/network allowlists).
2. Re-export with that URL; confirm one server, 17 operation names and no admin tools.
3. Import and bind credentials; invoke get_ticket_details on INC-1001 in draft.
4. Check a missing/wrong key returns 401, valid calls produce typed JSON, and retry actions do not duplicate logs.
5. Exercise the four documented demos, then validate live bindings if deploying the agents.

No tenant credentials or public endpoint were supplied. No Orchestrate import or live execution is claimed.

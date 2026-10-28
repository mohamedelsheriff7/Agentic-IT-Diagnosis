# Diagnostic caller contract — 1.0 (v6.6 and v6.7)

The user sees conversational text. A caller receives a separate result with `contract_version="1.0"`, described in [diagnostic-result.schema.json](diagnostic-result.schema.json).

## Access

- Native graph: `output["diagnostic_result"]` after invoking the compiled factory.
- Assistant metadata: `message.additional_kwargs["isys_diagnostic"]["diagnostic_result"]`.
- Local HTTP: `POST /langgraph/chat` returns `diagnostic_result` alongside `reply` and legacy fields. Reuse `session_id` to continue.

The root output and metadata copies are tested for agreement. Actual consumption of the root field by a WXO Supervisor still needs acceptance testing in the tenant. Visible chat alone is not the machine interface.

## Fields and decisions

| Field | Meaning |
|---|---|
| `ticket_id` | Active exact ticket ID; null before a ticket is selected |
| `diagnostic_result_id`, `diagnostic_result_version` | Actual backend checkpoint reference when available; null for local/unrecorded results |
| `diagnosis` | Canonical code, or null when no defensible diagnosis is established |
| `evidence`, `evidence_ids` | Saved observations and recorded references; user reports remain distinct from diagnostic checks |
| `confidence`, `confidence_basis` | LOW/MEDIUM/HIGH and observed basis; not a probability |
| `recommended_action` | ASK_MORE, RESOLVE, ROUTE, ESCALATE, or NONE for no action |
| `rationale`, `next_question` | Concise decision explanation and outstanding question |
| `knowledge_sources`, `historical_ticket_ids` | Source references, where available |
| `trace` | Candidates, observations, eliminations and decision checkpoints |
| `resolution_progress` | Exact step IDs and WAIT_STEP/WAIT_SUCCESS/RESOLVED or HUMAN_REQUIRED stage |
| `completed_actions` | Confirmed completed operations; a recommendation alone does not populate a success claim |
| `error` | Failure/configuration detail, otherwise null |

`recommended_action=RESOLVE` can mean a fix is ready or awaiting confirmation. Treat only `outcome=RESOLVED` with `TICKET_RESOLVED` in `completed_actions` as successful ticket resolution. ROUTE and ESCALATE are handoffs/recommendations; this agent does not assign specialists or create global tickets. ASK_MORE is an intermediate state, not a fourth final disposition.

## KB-001 guided resolution

The backend account check must provide recorded evidence for enabled=TRUE, locked=FALSE, password_expired=TRUE and mfa_locked=FALSE. The diagnosis also needs corroboration and applicable approved knowledge. Mandatory human restrictions always take precedence.

1. The agent presents backend KB-001 step `PASSWORD_EXPIRED-1`: use the organization's approved self-service password change flow. It never asks for a password or invents a portal URL.
2. The user explicitly confirms step completion. The agent stores the exact step ID and asks a separate question about the original sign-in problem.
3. Only explicit success confirmation permits the matching DIAGNOSED/HIGH/RESOLVE record and `resolve_ticket` call. An uncertain answer or failed fix leaves the ticket open.
4. Only backend success produces RESOLVED. No further mutation is attempted on the resolved ticket.

KB-027–038 are local guidance content, not backend resolution authorization. Their availability does not imply their steps have been performed.

# Tool catalog

All 17 tools require X-API-Key. See agent.openapi.yaml for typed schemas, examples and errors. Action IDs are required on state-writing operations, including diagnostic observations.

| Tool | Method and path | When to use |
|---|---|---|
| get_ticket_details | GET /tickets/{ticket_id} | Use before deciding next steps. Returns worklogs, related global issue, evidence and latest versioned diagnosis; no hidden answers. |
| search_similar_tickets | POST /tickets/search-similar | Use to compare symptoms with resolved/closed tickets. Deterministic lexical score is not diagnostic confidence; no useful overlap returns an empty list. |
| create_ticket | POST /tickets | Use when no ticket exists. Requires a synthetic reporter; preserves unknown classification. Supply a stable action_id for retries. |
| assign_ticket | POST /tickets/{ticket_id}/assignment | Use after diagnostic investigation. HIGH routes to requested group subject to review. MEDIUM routes to L1 preserving alternatives. LOW requires human triage. |
| add_worklog_entry | POST /tickets/{ticket_id}/worklogs | Use for intermediate reasoning and user responses. Cannot change status or owner. New evidence is limited to asserted user/knowledge/history sources; tool evidence comes only from checks. |
| resolve_ticket | POST /tickets/{ticket_id}/resolution | Use only after approved article conditions and steps are met, with recorded diagnosis and explicit user success confirmation. Mandatory human cases are rejected. Sets RESOLVED, never CLOSED. |
| count_recent_tickets | POST /tickets/count-recent | Use for outage investigation. Supplied filters use AND; requires a filter. Inclusive window excludes global, resolved, closed and already globally linked tickets. |
| find_open_global_tickets | POST /global-tickets/search | Use before creating a global issue. All supplied exact-match filters use AND; empty filters are rejected. Closed/resolved global issues are excluded. |
| create_global_ticket | POST /global-tickets | Use after the agent evaluates outage thresholds. Requires category, CI, location and active related tickets in that scope. Atomic linking and unique active scope prevent duplicates. |
| link_ticket_to_global_ticket | POST /tickets/{ticket_id}/global-link | Use when an active global issue already covers this exact category/CI/location. Conflicting, self and inactive links are rejected; identical links add no duplicate worklogs. |
| check_account_status | POST /diagnostics/account-status | Use to discriminate lockout, password expiry and MFA conditions. Reads stored state; unknown state remains UNKNOWN. Records evidence only, never modifies accounts or returns secrets. |
| check_application_entitlement | POST /diagnostics/application-entitlement | Use to distinguish missing entitlement or role from authentication failure. Reads stored provisioning state and records evidence; never grants access. |
| check_service_health | POST /diagnostics/service-health | Use to compare local symptoms with a stored service observation for the exact CI/location. Never infers health from ticket counts. Records evidence, with UNKNOWN when absent. |
| request_human_review | POST /tickets/{ticket_id}/human-reviews | Use for mandatory human cases or uncertainty. Sets PENDING and records a REQUESTED review; this is not approval. Only authenticated admin can decide a review. |
| notify_resolver_group | POST /tickets/{ticket_id}/notifications | Use after routing or escalation to record intended communication. Stores SQLite notification and worklog; sends no external message. |
| search_diagnostic_knowledge | POST /knowledge/search | Use to choose discriminating questions, safe checks and next steps. Returns approved portable articles with evidence, exclusions, resolution and escalation conditions. |
| record_diagnostic_result | POST /tickets/{ticket_id}/diagnostic-results | Use after collecting evidence. Stores agent assertions and confidence basis as a new version, validates sources/policy and updates valid taxonomy. Does not resolve or assign automatically. |

Developer/admin operations: GET /health, GET /docs, GET /openapi.json, POST /admin/human-reviews/{review_id}/decision. Only the last requires X-Admin-Key. Explicit reset/import is a local authenticated CLI, not an agent tool.

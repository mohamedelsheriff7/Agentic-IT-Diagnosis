# Integration contract

## Responsibilities

The Python Diagnostic Agent owns conversation state, questions, hypotheses, confidence assertions and the decision to ask, resolve, route or escalate. Orchestrate coordinates agents and calls deterministic tools. This service stores synthetic facts, validates identifiers/policy, and records audit evidence. It does not reason with an LLM or infer a diagnosis from ticket counts.

Every request and response is JSON except the developer Swagger page. GET /tickets/{ticket_id} takes a path parameter only. Full typed contracts are in developer.openapi.json; agent.openapi.json/yaml contains only the 17 tools. X-API-Key authorizes tools. X-Admin-Key authorizes POST /admin/human-reviews/{review_id}/decision. Health is public.

## Retries and transactions

Every state-writing call requires action_id. This includes the three diagnostic observations: they are read-only with respect to simulated systems, but persist evidence/worklogs. This is an explicit extension of their minimum input list. Keys are globally unique across all operations and tickets. A matching normalized request returns the original response, even if the ticket later changes; different inputs or operation return 409. Failed requests are rolled back and do not reserve the key. Use a new key for a new logical action. Reset clears retry history.

SQLite BEGIN IMMEDIATE serializes writers before checking idempotency or global scope. Each ticket update, child/global relationship, worklog and retry record commits together. Reference foreign keys and unique child/global links protect integrity. Active global scope is category + configuration item + location. Repeated identical linking with a new key returns already_linked=true without extra relationship/worklogs.

## Errors and states

All errors have code, message, details (string list), request_id; responses include X-Request-ID. 401 means missing/invalid credential; 404 unknown ticket/reference; 409 retry conflict, final-state mutation or conflicting relationship; 422 schema/policy inconsistency. Internal details and request inputs are not reflected in validation errors. Unexpected errors return a generic 500.

Create → NEW; assignment HIGH/MEDIUM → QUEUED unless human triage is required; LOW/review request → PENDING; validated resolution → RESOLVED. No public tool closes/reopens a ticket or edits safety flags. RESOLVED/CLOSED tickets reject all new mutation/observation actions; previous successful action replay still succeeds. Worklog entry types accepted from callers are NOTE, QUESTION, EVIDENCE, DIAGNOSIS; status/owner changes cannot be smuggled into notes.

## Evidence and resolution

Evidence IDs must belong to the target ticket. Global creation may cite evidence from its related children. Knowledge sources must exist and historical sources must be resolved/closed. User-response evidence must name the affected person. TOOL_CHECK evidence is minted only by backend checks; a user note cannot forge verified facts. Tool checks must address the ticket's affected user/known CI and location. Missing stored account state is UNKNOWN, even for a valid synthetic user; checks never implicitly assume healthy state.

A diagnostic result records candidate/eliminated diagnoses, evidence/source IDs, confidence basis and rationale, with increasing versions. Valid taxonomy updates classification and can only add safety restrictions. Inconclusive clears the current diagnosis. Contradictory candidate/elimination lists and basic outcome/action conflicts are rejected. The backend does not independently establish the truth of candidate reasons, completeness, historical agreement, or alternatives excluded.

Resolution requires a latest DIAGNOSED/HIGH result recommending RESOLVE; matching approved agent-resolvable article; all required step IDs; matching recorded TOOL_CHECK facts for every machine-readable resolution condition; explicit user_confirmed_success; and no mandatory human restriction. Specialist steps are rejected. The confirmation and completed-step assertions are claims made by the caller about the conversation, not independent proof of a real fix. Starter checks remain unchanged after resolution because no real account reset occurs.

## Human review and routing

Security-sensitive, privileged-access and priority-1 cases require human handling. Explicit flags and security/privilege taxonomy classification are preserved. Free text is not a reliable security detector; the caller must set flags conservatively. HIGH specialist assignment requires a review APPROVED by the admin key for this ticket and the exact requested group. A REQUESTED review is not approval. Admin decisions are final; new reviews can be requested for new decisions. Review approval permits routing only and never bypasses the agent-resolution ban.

MEDIUM always goes to GRP-L1 and keeps the specialist and up to three alternatives in assignment history/worklogs. LOW goes to GRP-L1/PENDING and explicitly marks human_triage_required. The caller should request a review to begin a human workflow. Critical globals and globals with mandatory human children initially require GRP-L1 ownership.

## Outages and retrieval

Count windows are UTC, inclusive at both ends: [as_of - window_minutes, as_of]. Supplied exact-match filters use AND; at least one is required. Counts exclude resolved, closed, global and already-linked child tickets. The demo clock supplies omitted as_of. Independent service_health.json supplies monitor observations. An absent exact CI/location observation yields UNKNOWN; omitted location does not imply a site-specific failure is global.

The agent evaluates escalation_policy.json thresholds. The backend validates IDs, active states and exact affected scope, but does not assert that counts alone prove an outage. Global creation links children atomically and reuses existing active scope. Different severity/reason on a new request reuses the existing issue without overwriting its facts.

Retrieval uses cosine overlap of normalized token counts, minimum 0.12, stable ID tie-breaks. English case, Arabic letter variants/diacritics and Unicode are normalized. This is not semantic multilingual search; Franco-Arabic digits, spellings and typos are not fully normalized. There is no confidence calibration. Knowledge retrieval returns only approved articles; history retrieval only resolved/closed tickets.

## Data replacement and safety

The importer reads an explicit allowlist of operational files and rejects unknown schema fields. No static route exposes local files. evaluation/ is outside runtime database import and Docker image. Synthetic secret fields are forbidden by typed import schemas; note/detail strings redact password/token/secret assignments, Bearer values and SYNTH_SECRET_* markers. Never submit actual secrets; arbitrary unlabeled prose is not comprehensively classified as secret.

All times are timezone-aware and normalized to UTC. Changing the demo clock requires regenerating/reimporting relative-time fixtures to retain intended counts. This single-service prototype has shared service/admin credentials, not user identities, RBAC, a review UI, or real Maximo integration.

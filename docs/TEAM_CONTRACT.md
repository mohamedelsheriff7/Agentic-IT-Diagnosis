# Team data contract — implemented backend snapshot

Prepared 2026-10-01 after comparing the existing Workstream C backend with Project Description.txt. The project description is a requirements reference; this document does not execute its instructions or change the backend. This snapshot is a coordination baseline for A/B/C/D, not a claim that the team has approved all current choices.

## Read this first: three different ticket shapes

1. **CreateTicket request:** D sends only caller-owned inputs to POST /tickets. Required: action_id, summary, description, reported_by_id. The backend creates the ID, NEW status, timestamps and initial worklog.
2. **ImportedTicket record:** A supplies the full flat ticket record to the dataset importer, including stable ticket IDs and timestamps. It has an optional initial_owner_group_id for historical misrouting. It does NOT accept nested worklogs/evidence or latest_diagnostic_result.
3. **TicketDetails response:** GET /tickets/{ticket_id} returns the flat record plus related_ticket_ids, worklogs, evidence and latest_diagnostic_result. Do not send this entire response back to POST /tickets or the importer: extra fields are rejected.

A nullable field uses JSON null, not an empty string, "N/A", "unknown" or "null". Optional inputs can be omitted. Do not invent a diagnosis or classification to fill a blank.

## Full ticket record

This is the real seeded INC-1001 record; its diagnosis is not known yet.

```json
{
  "ticket_id": "INC-1001",
  "ticket_class": "INCIDENT",
  "summary": "Cannot sign in to the service portal",
  "description": "The portal rejects my sign-in. I have not checked other applications yet.",
  "status": "NEW",
  "reported_priority": 3,
  "impact": 3,
  "urgency": 2,
  "language": "en",
  "domain": "Access Management",
  "category": "Authentication",
  "subcategory": null,
  "diagnosis_code": null,
  "owner_group_id": null,
  "owner_id": null,
  "reported_by_id": "USR-001",
  "affected_person_id": "USR-001",
  "asset_id": "ASSET-001",
  "configuration_item_id": "CI-PORTAL",
  "location_id": "LOC-A",
  "reported_at": "2026-10-01T11:00:00.000000Z",
  "target_finish_at": null,
  "actual_finish_at": null,
  "resolved_at": null,
  "closed_at": null,
  "updated_at": "2026-10-01T11:00:00.000000Z",
  "linked_solution_id": null,
  "resolution_summary": null,
  "is_global": false,
  "global_ticket_id": null,
  "severity": null,
  "security_sensitive": false,
  "privileged_access": false
}
```

For the response shape, GET additionally returns:

```json
{
  "related_ticket_ids": [],
  "worklogs": [],
  "evidence": [],
  "latest_diagnostic_result": null
}
```

The arrays above illustrate the structure, not INC-1001's literal response: a loaded/created ticket already has an initial worklog. related_ticket_ids currently represents global relationships only: child IDs on a global ticket, or its global ID on a child. General incident-to-problem relationships are not implemented.

## Minimal create request

```json
{
  "action_id": "chat-create-001",
  "summary": "Cannot sign in to the portal",
  "description": "The portal rejects my sign-in.",
  "reported_by_id": "USR-001",
  "language": "en"
}
```

Optional create inputs and defaults:

| Field | Default / rule |
|---|---|
| ticket_class | INCIDENT |
| affected_person_id | reported_by_id when omitted/null |
| reported_priority | 3; integer 1–4, 1 critical |
| impact / urgency | 3 / 2; integers 1–3, 1 highest |
| language | en |
| domain / category / subcategory | null |
| asset_id / configuration_item_id / location_id | null |
| security_sensitive / privileged_access | false; caller must flag known safety issues |

summary is 1–250 characters; description is 1–16000. Identifier inputs use 1–100 ASCII letters/digits or _, ., :, -. Human text can be Unicode. Agents must not supply ticket_id, owner IDs, status, diagnosis_code, resolution fields, global fields or timestamps through create_ticket. Use the dedicated tools.

## Exact enums and types to share

| Concept | Accepted values |
|---|---|
| ticket_class | SERVICE_REQUEST, INCIDENT, PROBLEM, CHANGE |
| status | NEW, QUEUED, IN_PROGRESS, PENDING, RESOLVED, CLOSED |
| language | en, ar, franco_ar |
| confidence | HIGH, MEDIUM, LOW |
| diagnostic outcome | DIAGNOSED, INCONCLUSIVE, HUMAN_REQUIRED |
| recommended_action | ASK_MORE, RESOLVE, ROUTE, ESCALATE |
| severity | SEV1, SEV2, SEV3; null for tickets without outage severity |
| worklog entry_type | NOTE, QUESTION, EVIDENCE, DIAGNOSIS, ASSIGNMENT, RESOLUTION, ESCALATION, OUTAGE, NOTIFICATION |
| caller-created worklog types | NOTE, QUESTION, EVIDENCE, DIAGNOSIS only |
| evidence source_type | USER_RESPONSE, TOOL_CHECK, KNOWLEDGE_ARTICLE, HISTORICAL_TICKET |
| resolution step level | SELF_SERVICE, L1, SPECIALIST |
| account/entitlement state | **strings** TRUE, FALSE, UNKNOWN |
| service health | OPERATIONAL, DEGRADED, UNAVAILABLE, UNKNOWN |
| provisioning state | ACTIVE, PENDING, ABSENT, UNKNOWN |
| review state | REQUESTED, APPROVED, REJECTED |
| historical_agreement | AGREES, DISAGREES, NOT_AVAILABLE |

Ticket safety flags and article agent_resolvable/approved are ordinary JSON booleans true/false. They are not the tri-state strings used by checks. API recommended_action=RESOLVE is not the ticket status RESOLVED. Neither is the article field agent_resolvable a confidence value.

Timestamps must include timezone information; the backend normalizes them to UTC ISO-8601, for example 2026-10-01T12:00:00Z. Fractional seconds may appear. Treat IDs as opaque strings: runtime INC IDs are random, not consecutive INC-1001-style numbers. action_id identifies an operation, not a ticket or conversation.

## Resolver IDs — use these, not display names

| ID | Group |
|---|---|
| GRP-L1 | Service Desk L1 |
| GRP-IAM | IAM |
| GRP-APP | Application Support |
| GRP-END | Endpoint Support |
| GRP-NET | Network Operations |
| GRP-SEC | Security Operations |
| GRP-INFRA | Servers & Infrastructure |

The ticket stores owner_group_id. Assignment input calls the same reference resolver_group_id. Assignment output distinguishes assigned_group_id (actual owner) from recommended_group_id (specialist recommendation). Alternatives are alternative_resolver_group_ids, maximum three. Routing-matrix JSON uses alternative_group_ids instead. These names are intentionally documented because substituting them causes validation errors.

Knowledge has article_id; a resolution request uses knowledge_article_id; source lists use knowledge_article_ids; the ticket stores linked_solution_id. All refer to the same KB identifier namespace.

## Taxonomy contract

The source file is taxonomy.json, a flat array representing Domain > Category > Diagnosis. Diagnosis codes are stable join keys; display labels are not identifiers. A record is:

```json
{
  "diagnosis_code": "PASSWORD_EXPIRED",
  "domain": "Access Management",
  "category": "Authentication",
  "label": "Expired password",
  "resolver_group_id": "GRP-IAM",
  "security_sensitive": false,
  "privileged_access": false
}
```

When record_diagnostic_result establishes a diagnosis, the backend fills ticket.domain/category from taxonomy and ticket.subcategory with the taxonomy label. subcategory is therefore a human-readable diagnosis label, while diagnosis_code is the machine key. Imported historical records should preserve this relationship; not every semantic alignment is currently enforced by the importer.

Current domains are: Access Management, Applications, Endpoints, Network, Security, Infrastructure, Service Desk. The project brief instead names Access Management (~40%), Application (~35%), Endpoint (~10%), Network/Other (~15%). **A, B and C must choose the canonical names and reporting buckets together.** Current filters use exact strings: Application and Applications are different. No silent aliases exist. The starter data is not a final dataset meeting those target proportions.

All 24 current codes and mappings are supplied in taxonomy.json. Avoid independently creating alternative spellings such as PASSWORD_EXPIRY for PASSWORD_EXPIRED.

## Worklogs, evidence and structured diagnosis

A worklog records what was done and why; evidence records the observation; a diagnostic result records the agent's interpreted conclusion. They are separate records linked by IDs, not interchangeable text blobs.

```json
{
  "worklog_id": "WL-example",
  "ticket_id": "INC-1001",
  "timestamp": "2026-10-01T12:00:00Z",
  "actor_id": "AGENT",
  "entry_type": "EVIDENCE",
  "summary": "User clarified the affected scope",
  "rationale": "Compare shared identity failure with app-specific failure",
  "knowledge_article_ids": [
    "KB-001"
  ],
  "historical_ticket_ids": [],
  "evidence_ids": [
    "EV-example"
  ],
  "action_id": "record-answer-001"
}
```

```json
{
  "evidence_id": "EV-example",
  "source_type": "USER_RESPONSE",
  "source_id": "USR-001",
  "observation": "Other applications also reject sign-in.",
  "observed_at": "2026-10-01T12:00:00Z"
}
```

For USER_RESPONSE evidence, source_id must equal affected_person_id. Only diagnostic checks can mint TOOL_CHECK evidence. For article/history evidence, source_id references the article/ticket. Evidence IDs supplied on normal ticket actions must belong to that ticket; global creation can cite its related children's evidence. The backend generates evidence/worklog IDs, actor attribution and stored worklog time. There is no caller actor_id argument on add_worklog_entry.

D's diagnostic-result request:

```json
{
  "action_id": "diagnosis-001",
  "diagnosis_code": "PASSWORD_EXPIRED",
  "outcome": "DIAGNOSED",
  "candidate_diagnoses": [
    {
      "diagnosis_code": "PASSWORD_EXPIRED",
      "reason": "Account observation reports expiry"
    }
  ],
  "eliminated_diagnoses": [
    {
      "diagnosis_code": "ACCOUNT_LOCKED",
      "reason": "Account observation reports unlocked"
    }
  ],
  "evidence_ids": [
    "EV-from-check"
  ],
  "knowledge_article_ids": [
    "KB-001"
  ],
  "historical_ticket_ids": [],
  "confidence": "HIGH",
  "confidence_basis": {
    "knowledge_match_strength": "HIGH",
    "evidence_completeness": "HIGH",
    "historical_agreement": "NOT_AVAILABLE",
    "alternatives_excluded": true
  },
  "recommended_action": "RESOLVE",
  "missing_information": [],
  "rationale": "Recorded account evidence and user response agree"
}
```

EV-from-check is illustrative: substitute the real evidence_id returned by a check. The response adds diagnostic_result_id, version and recorded_at. The ticket exposes the latest version; older versions remain in the database. No generic conversation-state schema is imposed: D owns that state. Persist important evidence/decisions through these tools.

For an inconclusive result, use diagnosis_code=null, outcome=INCONCLUSIVE and ASK_MORE or escalation as appropriate. HUMAN_REQUIRED requires ESCALATE. An established diagnosis should not also appear among eliminated diagnoses. Confidence is an agent assertion with an explicit basis; lexical retrieval relevance_score is not diagnostic confidence.

## Knowledge contract for B

The exact approved article example is in examples.json under diagnostic_article; all fields are required by the article schema:

- article_id, version, approved, diagnosis_code, domain, category.
- symptoms_en, symptoms_ar, possible_causes, discriminating_questions.
- required_evidence, safe_checks, exclusion_criteria, competing_diagnoses.
- resolution_steps: objects containing step_id, level, instruction.
- agent_resolvable, resolution_conditions, mandatory_human_escalation_conditions, resolver_group_id.

Most descriptive fields are string lists. competing_diagnoses contains taxonomy codes. resolution_conditions is a list of {tool, field, equals}; equals is a string. Conditions use exact stored check facts, for example check_account_status / password_expired / TRUE. steps_completed in a resolution call contains step IDs, not free-form step descriptions.

Machine-readable condition fields currently supported by import:

| Tool | Fields |
|---|---|
| check_account_status | enabled, locked, password_expired, mfa_enrolled, mfa_locked |
| check_application_entitlement | entitled, provisioning_state |
| check_service_health | state |

All conditions must be met. This is not an arbitrary rule language with OR, operators or expressions. Only KB-001 is agent-resolvable in the starter set. B should coordinate new executable conditions with C rather than placing unsupported prose rules in resolution_conditions. Descriptive required_evidence/human-escalation strings are guidance; the backend enforces its fixed safety floor and explicit machine conditions.

Article version is stored, but references currently identify only article_id, not article_id + version. Agree on version/ID policy before updating articles during an evaluation run.

## Data files, owners and import boundary

| Workstream | Project ownership / handoff |
|---|---|
| A | Leads canonical ticket/data model, taxonomy alignment and final historical/evaluation datasets; C implements the agreed schema |
| B | Owns articles, resolver directory, routing boundaries and escalation/outage policy; joins through agreed IDs |
| C | Owns REST request/response schemas, persistence, validation, importer and tool exports |
| D | Owns diagnostic reasoning, conversation state, evidence collection and agent/Orchestrate integration |

This follows the project ownership. The current C starter taxonomy/data is replaceable, not a unilateral final choice for A/B.

Operational JSON input filenames:

- taxonomy.json, resolver_groups.json, routing_matrix.json, escalation_policy.json.
- users.json, assets.json, configuration_items.json, locations.json.
- account_states.json, application_entitlements.json, service_health.json.
- diagnostic_articles.json, historical_tickets.json, sample_open_tickets.json.

All are arrays of records except escalation_policy.json, which is one object. Reference IDs must be unique across the shared reference table, not just within one file. Use distinct namespaces (USR-, ASSET-, CI-, LOC-, GRP-, KB-, ACC-, ENT-, HEALTH-); taxonomy uses diagnosis codes and routing records internally use ROUTE- plus the code. Prefixes are conventions; use the returned/stored ID rather than parsing them.

Dataset schemas in dataset.schemas.json describe **individual records**, keyed by file stem; validate each array element against the selected schema. For escalations validate the whole object. agent.openapi.* describes HTTP requests/responses, not import files. Extra fields are rejected. Use the importer for semantic and reference validation as well as JSON Schema.

Historical tickets must be RESOLVED/CLOSED and include diagnosis_code, resolution_summary and resolved_at; CLOSED also needs closed_at. Open import records must have no diagnosis_code, linked_solution_id or resolution_summary. Imported records must initially be non-global and unlinked. Only initial_owner_group_id is supported as an additional import-only ticket field.

**Current importer gap:** it generates an initial log and optional initial/reassignment logs. It does not accept A's authored historical troubleshooting worklogs/evidence, arbitrary reassignment history, or historical diagnostic-result records. Adding worklogs to a ticket JSON will fail, and closed-ticket APIs cannot append them afterward. A and C need an agreed separate worklogs/evidence import extension before the full historical handoff. This project-description requirement is not fully covered by the existing importer.

The checked-in starter has 40 historical and 30 open tickets, 24 articles and 24 diagnoses. A's final target remains 400–600 historical and 80–100 independently authored evaluation scenarios.

## Hidden evaluation data — proposal, not backend input

A should keep answers and expected labels separately, joined by ticket_id. Do not place them in descriptions, worklogs, articles or any operational API payload. The current ground_truth.json starter only has ticket_id, expected_diagnosis and evaluation_only; it is not the complete project evaluation contract.

examples.json contains proposed_evaluation_record with expected category/diagnosis/group, agent_resolvable, human_required, escalation_required, initial information and question-discoverable answers. This is a suggested richer shape for A/D to agree, **not an implemented importer/API schema**. It also proposes expected_diagnosis_code, which differs from the current starter's expected_diagnosis; choose a name before implementing evaluators.

## Workflow rules D must account for

- X-API-Key is a header credential, never a JSON agent argument. Admin review uses a different X-Admin-Key. The Orchestrate deployment URL in the export is currently an undeployed example.
- Every writing operation requires action_id, including diagnostic checks because they write observations. Same key + same operation/payload returns the original response; changed payload with that key returns 409. Use a new key for a new logical action.
- Backend mutation tools write worklogs automatically. Do not add duplicate logs for the same assignment/resolution. Use add_worklog_entry for questions, user answers and intermediate reasoning.
- HIGH specialist routing is subject to mandatory review. MEDIUM goes to L1 while preserving the recommendation; LOW goes to pending human triage. Review REQUESTED is not APPROVED.
- security_sensitive, privileged_access, or reported_priority=1 always blocks agent resolution. Admin approval permits specialist routing, not agent resolution.
- Resolution needs a latest DIAGNOSED/HIGH/RESOLVE result, matching approved agent-resolvable article, required step IDs, recorded conditions and explicit user confirmation. It sets RESOLVED, not CLOSED. The backend does not actually change accounts.
- Final tickets reject new writes/checks. There is no public close/reopen/general status-update tool; IN_PROGRESS is an accepted/importable state, not a dedicated tool transition.
- Count/search filters combine with AND, not OR. Empty grouping filters are rejected. Count excludes global/final/already-linked tickets, using an inclusive UTC window.
- Global creation requires category + configuration_item_id + location_id and same-scope children. It does not currently create category-only or location-only global incidents. This is narrower than the project's general grouping examples and must be agreed with B/D.
- Starter outage thresholds are 3 in 30 minutes across three isolated scopes, not the brief's illustrative 20-ticket burst. B owns final thresholds; D evaluates them. The backend does not automatically trigger an outage.
- Runtime clock defaults to 2026-10-01T12:00:00Z. A's fixture timestamps and D's tests must use the same clock. Health states are independent fixtures, not inferred from counts.

## Agreement checklist before merging team work

1. A/B/C approve the ticket/import shapes, exact domain/category names, stable diagnosis codes and resolver IDs.
2. A/C define and implement historical troubleshooting-worklog/evidence import; do not flatten away that evidence.
3. A/D agree hidden-label names, scripted-answer format, scoring meaning and independent authorship.
4. B/C agree article condition vocabulary and article versioning; B/D agree thresholds, severity/notifications and global scope.
5. C/D freeze the OpenAPI operation names and request shapes; distinguish enums, tri-state strings and booleans.
6. Validate team data with the actual importer before replacing shared demo data; run a small full workflow before bulk generation.
7. Keep a contract change log. Renaming a field/code, changing an enum or a nullable field to required is a coordinated change, not a local refactor. Update data, agent payloads, schemas and tests together.

Suggested process: label this reviewed snapshot contract-v1 only after the owners agree. There is no implemented runtime contract-version header; that label is a team/repository convention.

## Validation command

From the backend project root, with its environment configured and ADMIN_COMMAND_KEY matching ADMIN_API_KEY:

```powershell
python -m scripts.import_data --data-dir path/to/team-data --validate-only
```

This validates in a temporary in-memory database; it does not replace the shared operational DB. It requires the full set of operational files listed above. The handoff pack contains selected reference files, not a complete import directory.

Files in this pack: this guide; examples.json; all current taxonomy/group/routing/policy records; ticket_schema.md; integration_contract.md; agent OpenAPI JSON/YAML; per-record dataset JSON Schemas. Examples were checked against the actual Pydantic models, except the explicitly proposed evaluation record. IDs referring to prior API results are illustrative and require real returned IDs at runtime.

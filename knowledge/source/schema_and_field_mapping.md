# Workstream B schema and field mapping

Revision: 15 October 2026. JSON is the source for structured integration; PDFs are readable retrieval references. Authoring files and strict backend-import views have different purposes.

## Canonical identifiers and taxonomy

Join by diagnosis_code, never by display labels. Article references use backend-aligned article_id. Existing C IDs retain their meanings; KB-025 = VPN_CLIENT_ISSUE and KB-026 = ACCOUNT_LOCKED_POLICY. Use article_id_migration.json to translate original B IDs by diagnosis. Revised article versions are incremented; runtime references still identify by article_id alone, so coordinate replacement before evaluation.

Use taxonomy.json's exact domain/category values. Canonical backend domain names include Access Management, Applications, Endpoints, Network, Infrastructure, Security and Service Desk. The original four broad reporting buckets are not exact runtime domain filters. CERT_EXPIRED routes to GRP-INFRA. Resolver IDs are GRP-L1, GRP-IAM, GRP-APP, GRP-END, GRP-NET, GRP-SEC and GRP-INFRA.

## Article fields

| Field | Meaning |
|---|---|
| article_id, version, approved | Stable runtime reference, revision, approval gate; all current articles are unapproved |
| diagnosis_code, domain, category | Diagnosis join key and canonical runtime classification |
| symptoms_en, symptoms_ar | English/Arabic retrieval and symptom terminology |
| possible_causes | Hypotheses, not established facts |
| required_evidence | Observations needed to confirm diagnosis |
| discriminating_questions | Questions intended to distinguish competing causes |
| safe_checks | Checks to request only through implemented tools or documented human observations |
| exclusion_criteria, competing_diagnoses | Evidence that rules a diagnosis out and alternative diagnosis codes |
| resolution_steps | Ordered step_id, level and instruction; levels SELF_SERVICE, L1 or SPECIALIST |
| agent_resolvable | Proposed eligibility; does not override approved=false or safety gates |
| resolution_conditions | Exact tool/field/equals triples backed by recorded TOOL_CHECK evidence |
| mandatory_human_escalation_conditions | Additional human/safety conditions |
| resolver_group_id | Exact resolver reference |

## Strict backend import views

| Authoring file | Backend view and transformation |
|---|---|
| diagnostic_articles.json | Same article field contract; draft approval is retained |
| taxonomy.json | Same canonical taxonomy contract |
| resolver_groups.json | id <- resolver_group_id; label <- name. Scope and boundaries remain in authoring knowledge/PDF |
| routing_matrix.json | diagnosis_code; owner_group_id <- resolver_group_id; boundary <- routing_notes; alternative_group_ids. Confidence/human metadata remains in agent policy knowledge |
| escalation_policy.json | Backend id, mandatory_human_cases, severity_rules, outage_thresholds only. Threshold rows use category, configuration_item_id, location_id, window_minutes, minimum_count |

Backend schema rejects extra fields. Use backend_import/ for compatible partial reference replacements; rich root files cannot all be imported directly. The import policy has no approved/version/notification fields; the external approval register and agent policy govern those decisions. Runtime assignment requests use alternative_resolver_group_ids; routing reference rows use alternative_group_ids.

## Ticket mapping

| Ticket field | Use |
|---|---|
| ticket_id, ticket_class | Identity and INCIDENT/SERVICE_REQUEST/PROBLEM/CHANGE |
| summary, description | Initial symptoms, not conclusive diagnosis |
| status | NEW, QUEUED, IN_PROGRESS, PENDING, RESOLVED, CLOSED lifecycle |
| reported_priority, impact, urgency | Triage inputs; priority 1 mandates human handling |
| domain, category, subcategory, diagnosis_code | Classification and stable diagnosis code |
| owner_group_id, initial_owner_group_id | Current owner and historical first assignment |
| configuration_item_id, location_id | Exact outage scope; both required for global creation |
| security_sensitive, privileged_access | Mandatory-human flags; no agent resolution |
| linked_solution_id | Approved article used in resolution |
| resolution_summary, resolved_at, actual_finish_at | Resolution audit fields |
| evidence_ids, knowledge_article_ids, historical_ticket_ids | Traceable sources in worklogs and diagnostic/action records |

## Implemented checks and conditions

- check_account_status: enabled, locked, password_expired, mfa_enrolled, mfa_locked; exact TRUE/FALSE/UNKNOWN strings.
- check_application_entitlement: entitled (TRUE/FALSE/UNKNOWN), provisioning_state (ACTIVE/PENDING/ABSENT/UNKNOWN).
- check_service_health: state (OPERATIONAL/DEGRADED/UNAVAILABLE/UNKNOWN).

Only backend checks mint TOOL_CHECK evidence. Check user_id must target the affected person; service checks must match known ticket CI/location. Every state-writing call, including evidence-producing checks, needs an action_id retry key. Missing observations return UNKNOWN and do not satisfy TRUE/FALSE conditions.

## Outage and notification contract

POLICY-DEFAULT defines three 3-ticket/30-minute scopes: VPN/CI-VPN/LOC-A; Availability/CI-PORTAL/LOC-B; Availability/CI-ERP/LOC-C. Count Recent Tickets uses inclusive UTC boundaries and AND filters, excluding final/global/linked tickets. Align as_of with demo fixture dates.

Create Global Ticket needs category, CI, location, severity, owner and related active tickets. The agent evaluates thresholds and corroborating evidence; the backend does not infer outages. New SEV1 globals and globals with mandatory-human children require L1 ownership. Existing globals are reused without severity/owner overwrite.

Notifications accept resolver_group_id and severity and produce MOCK delivery records. L1 coordinates any human incident lead; no direct incident-lead recipient is implemented.

## Retrieval records

Current JSON/CSV logs contain matching NOT_RUN cases with expected aligned article IDs and empty actual results. The original logs remain under archive/ with old IDs and historical PASS values. They must not be combined into a current success rate. Approval status is separate from retrieval validation; Orchestrate PDF retrieval itself does not enforce backend approval.

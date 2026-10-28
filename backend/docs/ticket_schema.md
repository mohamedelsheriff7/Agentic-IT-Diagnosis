# Ticket schema

Field types follow the Pydantic contract. All nullable fields are explicit; all timestamps are timezone-aware UTC. Server generates IDs and timestamps.

| Field | JSON schema type | Meaning |
|---|---|---|
| ticket_id | string | Ticket id |
| ticket_class | string | SERVICE_REQUEST, INCIDENT, PROBLEM, CHANGE |
| summary | string | Summary |
| description | string | Unicode long description; English, Arabic and Franco-Arabic |
| status | string | NEW, QUEUED, IN_PROGRESS, PENDING, RESOLVED, CLOSED |
| reported_priority | integer | 1 critical through 4 low; 1 requires human handling |
| impact | integer | 1 highest to 3 lowest |
| urgency | integer | 1 highest to 3 lowest |
| language | string | Language |
| domain | string / null | Domain |
| category | string / null | Category |
| subcategory | string / null | Subcategory |
| diagnosis_code | string / null | Nullable FK to a valid taxonomy diagnosis |
| owner_group_id | string / null | Owner group id |
| owner_id | string / null | Owner id |
| reported_by_id | string | Reported by id |
| affected_person_id | string | Affected person id |
| asset_id | string / null | Asset id |
| configuration_item_id | string / null | Configuration item id |
| location_id | string / null | Location id |
| reported_at | string | Server UTC creation/report time |
| target_finish_at | string / null | Target finish at |
| actual_finish_at | string / null | Actual finish at |
| resolved_at | string / null | Set only on successful resolution |
| closed_at | string / null | Historical/imported closure; API never auto-closes |
| updated_at | string | Last successful ticket mutation UTC time |
| linked_solution_id | string / null | Nullable FK to an approved diagnostic article |
| resolution_summary | string / null | Resolution summary |
| is_global | boolean | Whether this record is the global incident |
| global_ticket_id | string / null | Nullable FK to a global incident |
| severity | string / null | Severity |
| security_sensitive | boolean | Conservatively preserved human-review flag |
| privileged_access | boolean | Conservatively preserved human-review flag |

get_ticket_details additionally returns related_ticket_ids, worklogs, evidence, and latest_diagnostic_result. Worklogs contain actor, timestamp, type, summary, rationale, evidence IDs, knowledge/history IDs and action ID. Evidence contains source type/ID, observation and observed_at. Internal verified tool facts remain in the evidence table; tool responses expose typed observations.

Reference IDs resolve against typed reference_data rows; tickets also have a self-FK for global_ticket_id. Separate tables persist worklogs, evidence, relationships, diagnostic versions, assignments, reviews, notifications and idempotency. SQLite enforces foreign keys on every connection. Internal active_scope is unique and not exposed through API.

# Maximo IT conceptual field mapping

This is a Maximo IT-aligned mock, not a Maximo API implementation. "Verified concept" means IBM documentation describes the corresponding service-desk concept; it does not assert an exact current MBO/OSLC field name, data type or endpoint. Validate an actual deployment schema before writing an adapter.

IBM reference: [Implementing Tivoli Service Request Manager Service Desk, SG24-7579](https://www.redbooks.ibm.com/redbooks/pdfs/sg247579.pdf), ticket user information, classification/priority, asset/CI and global-issue concepts. [Maximo Asset Management, SG24-7640](https://www.redbooks.ibm.com/redbooks/pdfs/sg247640.pdf), ticket and global-ticket concepts. These historical IBM references support concept alignment; current Maximo IT implementation details are unverified.

| Backend field | Maximo concept / proposed mapping | Status |
|---|---|---|
| ticket_id | Ticket identifier | Proposed concept alignment / prototype extension; exact mapping unverified |
| ticket_class | Service request, incident, problem classes; CHANGE treatment is prototype-specific | Proposed concept alignment / prototype extension; exact mapping unverified |
| summary | Short description | Proposed concept alignment / prototype extension; exact mapping unverified |
| description | Long description | Proposed concept alignment / prototype extension; exact mapping unverified |
| status | Ticket lifecycle status (local enum is not guaranteed to match deployment synonyms) | Proposed concept alignment / prototype extension; exact mapping unverified |
| reported_priority | Reported priority | Verified concept; exact attribute unverified |
| impact | Impact | Verified concept; exact attribute unverified |
| urgency | Urgency | Verified concept; exact attribute unverified |
| language | Local conversation language | Proposed concept alignment / prototype extension; exact mapping unverified |
| domain | Local taxonomy domain, potentially a classification path | Proposed concept alignment / prototype extension; exact mapping unverified |
| category | Local taxonomy category, potentially a classification path | Proposed concept alignment / prototype extension; exact mapping unverified |
| subcategory | Local diagnosis label in a classification path | Proposed concept alignment / prototype extension; exact mapping unverified |
| diagnosis_code | Local diagnostic taxonomy code | Proposed concept alignment / prototype extension; exact mapping unverified |
| owner_group_id | Owner group | Proposed concept alignment / prototype extension; exact mapping unverified |
| owner_id | Owner | Proposed concept alignment / prototype extension; exact mapping unverified |
| reported_by_id | Reported by | Verified concept; exact attribute unverified |
| affected_person_id | Affected person | Verified concept; exact attribute unverified |
| asset_id | Associated asset | Proposed concept alignment / prototype extension; exact mapping unverified |
| configuration_item_id | Associated configuration item | Proposed concept alignment / prototype extension; exact mapping unverified |
| location_id | Location | Proposed concept alignment / prototype extension; exact mapping unverified |
| reported_at | Reported date | Proposed concept alignment / prototype extension; exact mapping unverified |
| target_finish_at | Target finish | Proposed concept alignment / prototype extension; exact mapping unverified |
| actual_finish_at | Actual finish | Proposed concept alignment / prototype extension; exact mapping unverified |
| resolved_at | Local resolution milestone | Proposed concept alignment / prototype extension; exact mapping unverified |
| closed_at | Local closure milestone | Proposed concept alignment / prototype extension; exact mapping unverified |
| updated_at | Local audit timestamp | Proposed concept alignment / prototype extension; exact mapping unverified |
| linked_solution_id | Solution/knowledge reference | Proposed concept alignment / prototype extension; exact mapping unverified |
| resolution_summary | Resolution/solution narrative | Proposed concept alignment / prototype extension; exact mapping unverified |
| is_global | Global issue flag | Verified concept; exact attribute unverified |
| global_ticket_id | Related global record | Verified concept; exact attribute unverified |
| severity | Local outage severity | Proposed concept alignment / prototype extension; exact mapping unverified |
| security_sensitive | Local safety policy flag | Proposed concept alignment / prototype extension; exact mapping unverified |
| privileged_access | Local safety policy flag | Proposed concept alignment / prototype extension; exact mapping unverified |

Additional structures: worklogs align conceptually with service-desk work logs; relationships with related/global records; knowledge IDs with solution records. Evidence fact storage, confidence basis, candidate/eliminated diagnoses, retry records, synthetic check state, mock notifications and review approval schema are prototype extensions. Priority/status/enum ranges and the unified CHANGE class are local choices, not a claim of Maximo fidelity.

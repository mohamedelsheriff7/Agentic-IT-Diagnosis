"""Generate field/tool reference docs and portable dataset JSON Schema from code."""
import json
from app.config import ROOT
from app.schemas import TicketOut
from app.dataset import REFERENCE_SCHEMAS,ImportedTicket
from app.main import create_app
from app.config import Settings


def main():
    schemas={name: model.model_json_schema() for name,model in REFERENCE_SCHEMAS.items()}
    schemas['historical_tickets']=ImportedTicket.model_json_schema()
    schemas['sample_open_tickets']=ImportedTicket.model_json_schema()
    (ROOT/'specs/dataset.schemas.json').write_text(json.dumps(schemas,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ticket=TicketOut.model_json_schema()
    rows=['# Ticket schema','','Field types follow the Pydantic contract. All nullable fields are explicit; all timestamps are timezone-aware UTC. Server generates IDs and timestamps.','', '| Field | JSON schema type | Meaning |','|---|---|---|']
    meanings={'reported_priority':'1 critical through 4 low; 1 requires human handling','impact':'1 highest to 3 lowest','urgency':'1 highest to 3 lowest','description':'Unicode long description; English, Arabic and Franco-Arabic','status':'NEW, QUEUED, IN_PROGRESS, PENDING, RESOLVED, CLOSED','ticket_class':'SERVICE_REQUEST, INCIDENT, PROBLEM, CHANGE','reported_at':'Server UTC creation/report time','updated_at':'Last successful ticket mutation UTC time','is_global':'Whether this record is the global incident','global_ticket_id':'Nullable FK to a global incident','diagnosis_code':'Nullable FK to a valid taxonomy diagnosis','linked_solution_id':'Nullable FK to an approved diagnostic article','security_sensitive':'Conservatively preserved human-review flag','privileged_access':'Conservatively preserved human-review flag','resolved_at':'Set only on successful resolution','closed_at':'Historical/imported closure; API never auto-closes'}
    for name,field in ticket['properties'].items():
        typ=field.get('type') or ' / '.join(v.get('type','reference') for v in field.get('anyOf',[]))
        rows.append(f"| {name} | {typ} | {meanings.get(name,name.replace('_',' ').capitalize())} |")
    rows+=['','get_ticket_details additionally returns related_ticket_ids, worklogs, evidence, and latest_diagnostic_result. Worklogs contain actor, timestamp, type, summary, rationale, evidence IDs, knowledge/history IDs and action ID. Evidence contains source type/ID, observation and observed_at. Internal verified tool facts remain in the evidence table; tool responses expose typed observations.','','Reference IDs resolve against typed reference_data rows; tickets also have a self-FK for global_ticket_id. Separate tables persist worklogs, evidence, relationships, diagnostic versions, assignments, reviews, notifications and idempotency. SQLite enforces foreign keys on every connection. Internal active_scope is unique and not exposed through API.']
    (ROOT/'docs/ticket_schema.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    app=create_app(Settings(database_url='sqlite:///:memory:'))
    catalog=['# Tool catalog','','All 17 tools require X-API-Key. See agent.openapi.yaml for typed schemas, examples and errors. Action IDs are required on state-writing operations, including diagnostic observations.','','| Tool | Method and path | When to use |','|---|---|---|']
    for path,methods in app.openapi()['paths'].items():
        for method,operation in methods.items():
            if 'agent-tools' in operation.get('tags',[]):
                catalog.append(f"| {operation['operationId']} | {method.upper()} {path} | {operation['description']} |")
    catalog+=['','Developer/admin operations: GET /health, GET /docs, GET /openapi.json, POST /admin/human-reviews/{review_id}/decision. Only the last requires X-Admin-Key. Explicit reset/import is a local authenticated CLI, not an agent tool.']
    (ROOT/'docs/tool_catalog.md').write_text('\n'.join(catalog)+'\n',encoding='utf-8')
    verified={'ticket_id':'Ticket identifier','ticket_class':'Service request, incident, problem classes; CHANGE treatment is prototype-specific','summary':'Short description','description':'Long description','status':'Ticket lifecycle status (local enum is not guaranteed to match deployment synonyms)','reported_priority':'Reported priority','impact':'Impact','urgency':'Urgency','owner_group_id':'Owner group','owner_id':'Owner','reported_by_id':'Reported by','affected_person_id':'Affected person','asset_id':'Associated asset','configuration_item_id':'Associated configuration item','location_id':'Location','reported_at':'Reported date','target_finish_at':'Target finish','actual_finish_at':'Actual finish','is_global':'Global issue flag','global_ticket_id':'Related global record','linked_solution_id':'Solution/knowledge reference','resolution_summary':'Resolution/solution narrative'}
    mapping=['# Maximo IT conceptual field mapping','','This is a Maximo IT-aligned mock, not a Maximo API implementation. "Verified concept" means IBM documentation describes the corresponding service-desk concept; it does not assert an exact current MBO/OSLC field name, data type or endpoint. Validate an actual deployment schema before writing an adapter.','','IBM reference: [Implementing Tivoli Service Request Manager Service Desk, SG24-7579](https://www.redbooks.ibm.com/redbooks/pdfs/sg247579.pdf), ticket user information, classification/priority, asset/CI and global-issue concepts. [Maximo Asset Management, SG24-7640](https://www.redbooks.ibm.com/redbooks/pdfs/sg247640.pdf), ticket and global-ticket concepts. These historical IBM references support concept alignment; current Maximo IT implementation details are unverified.','','| Backend field | Maximo concept / proposed mapping | Status |','|---|---|---|']
    # Narrow verified claims to fields directly evidenced in the consulted excerpts.
    confirmed={'reported_by_id','affected_person_id','reported_priority','impact','urgency','is_global','global_ticket_id'}
    for name in ticket['properties']:
        concept=verified.get(name,{'domain':'Local taxonomy domain, potentially a classification path','category':'Local taxonomy category, potentially a classification path','subcategory':'Local diagnosis label in a classification path','diagnosis_code':'Local diagnostic taxonomy code','resolved_at':'Local resolution milestone','closed_at':'Local closure milestone','updated_at':'Local audit timestamp','language':'Local conversation language','severity':'Local outage severity','security_sensitive':'Local safety policy flag','privileged_access':'Local safety policy flag'}.get(name,name))
        mapping.append(f"| {name} | {concept} | {'Verified concept; exact attribute unverified' if name in confirmed else 'Proposed concept alignment / prototype extension; exact mapping unverified'} |")
    mapping+=['','Additional structures: worklogs align conceptually with service-desk work logs; relationships with related/global records; knowledge IDs with solution records. Evidence fact storage, confidence basis, candidate/eliminated diagnoses, retry records, synthetic check state, mock notifications and review approval schema are prototype extensions. Priority/status/enum ranges and the unified CHANGE class are local choices, not a claim of Maximo fidelity.']
    (ROOT/'docs/maximo_field_mapping.md').write_text('\n'.join(mapping)+'\n',encoding='utf-8')
    print('Generated dataset schemas, field mapping and tool catalog')
if __name__=='__main__': main()

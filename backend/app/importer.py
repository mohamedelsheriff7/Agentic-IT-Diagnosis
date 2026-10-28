import json
from datetime import datetime
from sqlalchemy import delete, select
from . import models as m, repositories as repo, services as svc
from .dataset import REFERENCE_SCHEMAS, ImportedTicket
from .policy import fail, utc, redact


def read_dataset(folder):
    references=[]
    for name,schema in REFERENCE_SCHEMAS.items():
        rows=json.loads((folder/(name+'.json')).read_text(encoding='utf-8-sig'))
        if name=='escalation_policy': rows=[rows]
        for n,row in enumerate(rows):
            value=schema.model_validate(row).model_dump(mode='json')
            key=value.get('id') or value.get('article_id') or value.get('diagnosis_code')
            if name=='routing_matrix': key='ROUTE-'+key
            references.append((key,name,redact(value)))
    if len({r[0] for r in references})!=len(references): raise ValueError('Duplicate reference IDs')
    tickets=[]
    for name in ('historical_tickets','sample_open_tickets'):
        for row in json.loads((folder/(name+'.json')).read_text(encoding='utf-8-sig')):
            value=ImportedTicket.model_validate(row).model_dump(mode='json')
            historical=value['status'] in ('RESOLVED','CLOSED')
            if historical != (name=='historical_tickets'): raise ValueError('Ticket in wrong dataset')
            tickets.append(value)
    if len({t['ticket_id'] for t in tickets})!=len(tickets): raise ValueError('Duplicate ticket IDs')
    return references,tickets


def import_dataset(db,folder,reset=False):
    references,tickets=read_dataset(folder)
    if reset:
        for table in reversed(m.Base.metadata.sorted_tables): db.execute(delete(table))
    elif db.scalar(select(m.Ticket.ticket_id).limit(1)) or db.scalar(select(m.Reference.id).limit(1)):
        fail('Database is not empty; explicit reset is required','IMPORT_CONFLICT',409)
    for identifier,kind,value in references: db.add(m.Reference(id=identifier,kind=kind,data=value))
    db.flush()
    for _,kind,r in references:
        if kind in ('taxonomy','diagnostic_articles'): repo.reference(db,r['resolver_group_id'],'resolver_groups')
        if kind=='diagnostic_articles':
            tax=repo.reference(db,r['diagnosis_code'],'taxonomy')
            if (tax['domain'],tax['category'])!=(r['domain'],r['category']): fail('Article taxonomy mismatch')
            for code in r['competing_diagnoses']: repo.reference(db,code,'taxonomy')
            for c in r['resolution_conditions']:
                fields={'check_account_status':{'enabled','locked','password_expired','mfa_enrolled','mfa_locked'},'check_application_entitlement':{'entitled','provisioning_state'},'check_service_health':{'state'}}
                if c['field'] not in fields[c['tool']]: fail('Invalid article condition field')
            if r['agent_resolvable'] and (not r['resolution_conditions'] or any(s['level']=='SPECIALIST' for s in r['resolution_steps'])): fail('Agent-resolvable article must have safe steps and conditions')
        if kind in ('account_states','application_entitlements'): repo.reference(db,r['user_id'],'users')
        if kind=='service_health': svc.validate_context(db,r)
        if kind=='routing_matrix':
            repo.reference(db,r['diagnosis_code'],'taxonomy');repo.reference(db,r['owner_group_id'],'resolver_groups')
            for group in r['alternative_group_ids']: repo.reference(db,group,'resolver_groups')
        if kind=='escalation_policy':
            for threshold in r['outage_thresholds']: svc.validate_context(db,threshold)
    for b in tickets:
        svc.validate_context(db,b)
        if b['diagnosis_code']: repo.reference(db,b['diagnosis_code'],'taxonomy')
        if b['linked_solution_id']: repo.reference(db,b['linked_solution_id'],'diagnostic_articles')
        initial=b.pop('initial_owner_group_id',None)
        if initial: repo.reference(db,initial,'resolver_groups')
        for key in ('reported_at','target_finish_at','actual_finish_at','resolved_at','closed_at','updated_at'):
            if b[key]: b[key]=utc(datetime.fromisoformat(b[key].replace('Z','+00:00')))
        if b['is_global'] or b['global_ticket_id']: fail('Starter import expects unlinked individual tickets')
        t=m.Ticket(**redact(b));db.add(t);db.flush()
        saved_updated=t.updated_at
        svc.log(db,t,t.reported_at,'NOTE','Synthetic fixture imported','Explicit dataset load; no hidden evaluation fields.',actor='IMPORT')
        if initial and initial!=t.owner_group_id:
            svc.log(db,t,t.reported_at,'ASSIGNMENT','Initially routed to '+initial,'Historical misroute retained for evaluation.',actor='IMPORT')
            svc.log(db,t,saved_updated,'ASSIGNMENT','Reassigned to '+t.owner_group_id,'Specialist investigation corrected the initial routing.',actor='IMPORT')
            db.add(m.Assignment(id=svc.uid('ASG'),ticket_id=t.ticket_id,group_id=t.owner_group_id,data={'initial_group_id':initial,'reason':'Historical routing correction'}))
        t.updated_at=saved_updated
    db.flush()
    return len(tickets)

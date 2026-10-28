"""Explicit offline adapter: validate A's tickets/labels and prepare isolated data.

Only declared required_fixtures facts are projected into operational fixtures.
Expected diagnoses, labels and scripted answers are never imported into SQLite.
Original files are archived unchanged outside the operational data directory.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
import shutil
from sqlalchemy import select,func,text
from app.config import ROOT
from app.dataset import ImportedTicket
from app.evaluation_contract import EvaluationRecord
from app.importer import import_dataset
from app.models import database,Ticket

NEW_TAXONOMY=[
    dict(diagnosis_code='ACCOUNT_LOCKED_POLICY',domain='Access Management',category='Authentication',label='Account locked by security policy',resolver_group_id='GRP-SEC',security_sensitive=True,privileged_access=False),
    dict(diagnosis_code='VPN_CLIENT_ISSUE',domain='Network',category='VPN',label='VPN client or credential issue',resolver_group_id='GRP-NET',security_sensitive=False,privileged_access=False),
]

def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def when(value): return datetime.fromisoformat(value.replace('Z','+00:00'))

def validate_pair(tickets,labels,taxonomy,groups):
    for t in tickets: ImportedTicket.model_validate(t)
    for r in labels: EvaluationRecord.model_validate(r)
    if len({t['ticket_id'] for t in tickets})!=len(tickets): raise ValueError('Duplicate ticket IDs')
    if len({r['ticket_id'] for r in labels})!=len(labels): raise ValueError('Duplicate ground-truth IDs')
    by_id={t['ticket_id']:t for t in tickets}
    if set(by_id)!={r['ticket_id'] for r in labels}: raise ValueError('Tickets and labels must join exactly one-to-one')
    facts={}
    for label in labels:
        ticket=by_id[label['ticket_id']]
        code=label['expected_diagnosis_code']
        if code not in taxonomy: raise ValueError('Unknown evaluation diagnosis: '+code)
        if label['expected_resolver_group_id'] not in groups or label['expected_resolver_group_id']!=taxonomy[code]['resolver_group_id']: raise ValueError('Ground-truth group differs from taxonomy: '+ticket['ticket_id'])
        if label['expected_category']!=taxonomy[code]['category']: raise ValueError('Ground-truth category differs from taxonomy')
        for candidate in label['initial_candidates']:
            if candidate not in taxonomy: raise ValueError('Unknown candidate code: '+candidate)
        for answer in label['discoverable_information']:
            for eliminated in answer['eliminates']:
                if eliminated not in taxonomy: raise ValueError('Unknown eliminated code: '+eliminated)
        mandatory=ticket['reported_priority']==1 or ticket['security_sensitive'] or ticket['privileged_access'] or taxonomy[code]['security_sensitive'] or taxonomy[code]['privileged_access']
        if mandatory and (not label['human_required'] or label['agent_resolvable'] or label['expected_action']!='ESCALATE'): raise ValueError('Unsafe human policy label: '+ticket['ticket_id'])
        if label['agent_resolvable'] and label['expected_action']!='RESOLVE': raise ValueError('Resolvable label/action mismatch')
        if ticket['status']!='NEW' or ticket['is_global'] or ticket['global_ticket_id']: raise ValueError('Evaluation tickets must initially be NEW and unlinked')
        if any(ticket.get(k) for k in ('diagnosis_code','resolution_summary','linked_solution_id','subcategory')): raise ValueError('Hidden conclusion appears in operational ticket')
        if when(ticket['reported_at'])>when('2026-10-01T12:00:00Z'): raise ValueError('Evaluation report is after the agreed demo clock')
        for tool,values in label['required_fixtures'].items():
            if tool=='check_account_status': key=(tool,ticket['affected_person_id'])
            elif tool=='check_application_entitlement': key=(tool,ticket['affected_person_id'],values['application_id'])
            else:
                key=(tool,values['configuration_item_id'],values.get('location_id'))
                if ticket['configuration_item_id'] and ticket['configuration_item_id']!=values['configuration_item_id']: raise ValueError('Fixture CI contradicts ticket')
                if ticket['location_id'] and values.get('location_id') and ticket['location_id']!=values['location_id']: raise ValueError('Fixture location contradicts ticket')
            if key in facts and facts[key]!=values: raise ValueError('Conflicting stored fixture facts: '+str(key))
            facts[key]=values
    return facts

def prepare(ticket_path,truth_path,destination=None,archive=None):
    dest=Path(destination or ROOT/'data/workstream_a')
    archive=Path(archive or ROOT/'evaluation/workstream_a')
    dest.mkdir(parents=True,exist_ok=True);archive.mkdir(parents=True,exist_ok=True)
    tickets=read(ticket_path);labels=read(truth_path)
    taxonomy=read(ROOT/'data/taxonomy.json')
    known={t['diagnosis_code'] for t in taxonomy}
    taxonomy += [r for r in NEW_TAXONOMY if r['diagnosis_code'] not in known]
    groups=read(ROOT/'data/resolver_groups.json')
    facts=validate_pair(tickets,labels,{r['diagnosis_code']:r for r in taxonomy},{r['id'] for r in groups})
    # Keep source data archived verbatim, including hidden labels outside data/.
    shutil.copyfile(ticket_path,archive/'TestSet_Tickets.original.json')
    shutil.copyfile(truth_path,archive/'ground_truth.json')
    for path in (ROOT/'data').glob('*.json'): shutil.copyfile(path,dest/path.name)
    write(dest/'taxonomy.json',taxonomy)
    routes=read(dest/'routing_matrix.json')
    route_codes={r['diagnosis_code'] for r in routes}
    for t in NEW_TAXONOMY:
        if t['diagnosis_code'] not in route_codes:
            routes.append(dict(diagnosis_code=t['diagnosis_code'],owner_group_id=t['resolver_group_id'],boundary='Security-policy lockouts require Security Operations and human review.' if t['security_sensitive'] else 'Local VPN client/credential problems are distinct from a service-wide outage; Network Operations investigates.',alternative_group_ids=['GRP-L1']))
    write(dest/'routing_matrix.json',routes)
    reference_fields={'users':('reported_by_id','affected_person_id','owner_id'),'assets':('asset_id',)}
    added={}
    for name,fields in reference_fields.items():
        rows=read(dest/(name+'.json'));by_id={r['id']:r for r in rows}
        before=len(by_id)
        for ticket in tickets:
            for field in fields:
                identifier=ticket.get(field)
                if identifier and identifier not in by_id: by_id[identifier]=dict(id=identifier,label='Synthetic '+identifier)
        write(dest/(name+'.json'),sorted(by_id.values(),key=lambda r:r['id']))
        added[name]=len(by_id)-before
    # These are factual checks specified by A, not conclusions derived from labels.
    counters=Counter()
    for tool,file_name in [('check_account_status','account_states'),('check_application_entitlement','application_entitlements'),('check_service_health','service_health')]:
        rows=read(dest/(file_name+'.json'))
        def key_for(row):
            return (tool,row['user_id']) if tool=='check_account_status' else (tool,row['user_id'],row['application_id']) if tool=='check_application_entitlement' else (tool,row['configuration_item_id'],row.get('location_id'))
        by_key={key_for(row):row for row in rows}
        for key,value in facts.items():
            if key[0]!=tool: continue
            counters[tool]+=1
            row=dict(value)
            digest=hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]
            row['id']='A-'+{'check_account_status':'ACC-','check_application_entitlement':'ENT-','check_service_health':'HEALTH-'}[tool]+digest
            if tool in ('check_account_status','check_application_entitlement'): row['user_id']=key[1]
            if tool=='check_application_entitlement': row['roles']=[]
            if tool=='check_service_health': row.update(scope=f"{row['configuration_item_id']}/{row.get('location_id')}",details='Stored synthetic monitor fact supplied by Workstream A.')
            by_key[key]=row
        write(dest/(file_name+'.json'),list(by_key.values()))
    write(dest/'sample_open_tickets.json',tickets)
    write(dest/'outage_fixtures.json',dict(clock='2026-10-01T12:00:00Z',description='Workstream A evaluation uses neutral TST IDs. Cluster membership is held only in offline evaluation labels; use escalation_policy.json for operational scope thresholds.'))
    # Validate the actual operational data through SQLAlchemy/FKs, not just schemas.
    engine,sessions=database('sqlite:///:memory:')
    with sessions() as db:
        total=import_dataset(db,dest);db.commit()
        assert db.scalar(select(func.count()).select_from(Ticket).where(Ticket.ticket_id.like('TST-%')))==len(tickets)
    engine.dispose()
    counts=[]
    for cluster_id in sorted({r['cluster_id'] for r in labels if r['cluster_id']}):
        members=[t for t in tickets if t['ticket_id'] in {r['ticket_id'] for r in labels if r['cluster_id']==cluster_id}]
        max_count=max(sum(all(t[k]==m[k] for k in ('category','configuration_item_id','location_id')) and when(m['reported_at'])-timedelta(minutes=30)<=when(t['reported_at'])<=when(m['reported_at']) for t in tickets) for m in members)
        counts.append(dict(cluster_id=cluster_id,tickets=len(members),max_30_minute_count=max_count))
    result=dict(imported_total=total,historical=total-len(tickets),evaluation_tickets=len(tickets),labels=len(labels),scenario_counts=dict(Counter(r['scenario_type'] for r in labels)),references_added=added,fixture_records=dict(counters),clusters=counts,missing_articles=sorted({r['expected_diagnosis_code'] for r in labels}-{a['diagnosis_code'] for a in read(dest/'diagnostic_articles.json')}),source_sha256={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (ticket_path,truth_path)})
    write(archive/'validation_summary.json',result)
    write(archive/'ground_truth.schema.json',EvaluationRecord.model_json_schema())
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tickets',type=Path,required=True);p.add_argument('--ground-truth',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(prepare(args.tickets,args.ground_truth),indent=2))
if __name__=='__main__':main()

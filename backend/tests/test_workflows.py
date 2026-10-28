import json
from uuid import uuid4
import pytest
from sqlalchemy import select,func,text
from fastapi.testclient import TestClient
from app import models as m
from app.config import ROOT,Settings
from app.main import create_app


def post(client,path,body,expected=200):
    response=client.post(path,json=body)
    assert response.status_code==expected,response.text
    return response.json()

def action(**kw): return dict(action_id=uuid4().hex,**kw)
def get(client,ticket='INC-1001'): return client.get('/tickets/'+ticket).json()
def check(client,ticket='INC-1001',user='USR-001'):
    return post(client,'/diagnostics/account-status',action(ticket_id=ticket,user_id=user))
def diagnosis(code='PASSWORD_EXPIRED',**kw):
    return action(diagnosis_code=code,outcome='DIAGNOSED',candidate_diagnoses=[{'diagnosis_code':code,'reason':'Observed discriminating signal'}],eliminated_diagnoses=[],confidence='HIGH',confidence_basis={'knowledge_match_strength':'HIGH','evidence_completeness':'HIGH','historical_agreement':'NOT_AVAILABLE','alternatives_excluded':True},recommended_action='RESOLVE',missing_information=[],rationale='Agent reasoning assertion',**kw)
def resolution(evidence,**kw):
    b=action(diagnosis_code='PASSWORD_EXPIRED',resolution_summary='User completed safe self-service steps',steps_completed=['PASSWORD_EXPIRED-1'],knowledge_article_id='KB-001',user_confirmed_success=True,evidence_ids=[evidence]);b.update(kw);return b

def global_body(**kw):
    b=action(summary='VPN unavailable at site A',description='Multiple users affected',severity='SEV2',category='VPN',configuration_item_id='CI-VPN',location_id='LOC-A',owner_group_id='GRP-NET',related_ticket_ids=['CLUSTER-1-1','CLUSTER-1-2'],reason='Independent outage investigation');b.update(kw);return b


def test_get_ticket_full_and_auth(client):
    ticket=get(client)
    assert ticket['diagnosis_code'] is None and ticket['latest_diagnostic_result'] is None
    assert ticket['related_ticket_ids']==[] and len(ticket['worklogs'])==1
    assert client.get('/tickets/MISSING').status_code==404
    for headers in ({'X-API-Key':''},{'X-API-Key':'wrong'}):
        response=client.get('/tickets/INC-1001',headers=headers)
        assert response.status_code==401 and response.json()['request_id']
    assert client.get('/evaluation/ground_truth.json').status_code==404


def test_create_idempotency_and_worklog(client,app):
    b=action(summary='مش عارف ادخل',description='mesh shaghal',reported_by_id='USR-001')
    first=post(client,'/tickets',b)
    assert first['category'] is None and first['diagnosis_code'] is None
    assert first['status']=='NEW' and len(first['worklogs'])==1
    assert post(client,'/tickets',b)==first
    post(client,'/tickets',dict(b,summary='different'),409)
    assert client.get('/tickets/'+first['ticket_id']).json()==first
    with app.state.sessions() as db: assert db.scalar(select(func.count()).select_from(m.Ticket))==71

@pytest.mark.parametrize('change',[{'reported_priority':0},{'reported_priority':5},{'language':'de'},{'status':'RESOLVED'},{'summary':' '},{'ticket_class':'OTHER'},{'action_id':''}])
def test_create_invalid(client,change):
    post(client,'/tickets',action(summary='Issue',description='Issue',reported_by_id='USR-001')|change,422)

@pytest.mark.parametrize('field',['reported_by_id','affected_person_id','asset_id','configuration_item_id','location_id'])
def test_create_foreign_keys(client,field):
    post(client,'/tickets',action(summary='Issue',description='Issue',reported_by_id='USR-001')|{field:'MISSING'},404)


def test_history_and_knowledge_search(client):
    result=post(client,'/tickets/search-similar',{'description':'password expired sign in','limit':20})
    assert result['results'] and all(t['ticket_id'].startswith('HIST-') for t in result['results'])
    assert post(client,'/tickets/search-similar',{'description':'zzzzqwxq'})=={'results':[]}
    result=post(client,'/tickets/search-similar',{'description':'كلمة المرور انتهت'})
    assert result['results']
    kb=post(client,'/knowledge/search',{'query':'password expired'})['results']
    assert kb and all(k['approved'] for k in kb) and kb[0]['article_id']=='KB-001'
    assert kb[0]['resolution_conditions'] and kb[0]['discriminating_questions']


def test_note_evidence_redaction_and_no_assignment(client):
    b=action(entry_type='EVIDENCE',summary='password=SYNTH_SECRET_abc token=1234',rationale='Bearer abcd',evidence=[{'source_type':'USER_RESPONSE','source_id':'USR-001','observation':'The message says password expired. password=secret-test-value'}])
    out=post(client,'/tickets/INC-1001/worklogs',b)
    assert out['evidence_ids'] and 'secret-test-value' not in json.dumps(get(client))
    assert 'SYNTH_SECRET_abc' not in json.dumps(get(client))
    assert post(client,'/tickets/INC-1001/worklogs',b)==out
    post(client,'/tickets/INC-1001/worklogs',dict(b,action_id='new',owner_group_id='GRP-IAM'),422)
    assert get(client)['owner_group_id'] is None


def test_diagnostic_checks_fixed_states_and_retry(client):
    b=action(ticket_id='INC-1001',user_id='USR-001')
    first=post(client,'/diagnostics/account-status',b)
    assert first['password_expired']=='TRUE' and first['locked']=='FALSE'
    assert post(client,'/diagnostics/account-status',b)==first
    assert len(get(client)['evidence'])==1
    assert check(client,'INC-1002','USR-002')['locked']=='TRUE'
    entitlement=post(client,'/diagnostics/application-entitlement',action(ticket_id='INC-1004',user_id='USR-004',application_id='APP-PORTAL',required_role='USER'))
    assert entitlement['entitled']=='FALSE' and entitlement['provisioning_state']=='ABSENT'
    assert post(client,'/diagnostics/application-entitlement',action(ticket_id='INC-1001',user_id='USR-001',application_id='APP-UNKNOWN'))['entitled']=='UNKNOWN'
    health=post(client,'/diagnostics/service-health',action(ticket_id='CLUSTER-1-1',configuration_item_id='CI-VPN',location_id='LOC-A'))
    assert health['state']=='UNAVAILABLE'
    assert post(client,'/diagnostics/service-health',action(ticket_id='CLUSTER-1-1',configuration_item_id='CI-VPN'))['state']=='UNKNOWN'
    unknown=post(client,'/tickets',action(summary='No known state',description='Unclear',reported_by_id='USR-040'))
    assert check(client,unknown['ticket_id'],'USR-040')['enabled']=='UNKNOWN'
    post(client,'/diagnostics/account-status',action(ticket_id='MISSING',user_id='USR-001'),404)
    post(client,'/diagnostics/account-status',action(ticket_id='INC-1001',user_id='USR-002'),422)


def test_diagnose_version_and_resolution(client):
    evidence=check(client)['evidence_id']
    d=diagnosis(evidence_ids=[evidence],knowledge_article_ids=['KB-001'])
    result=post(client,'/tickets/INC-1001/diagnostic-results',d)
    assert result['version']==1 and post(client,'/tickets/INC-1001/diagnostic-results',d)==result
    assert get(client)['status']=='NEW' and get(client)['owner_group_id'] is None
    d['action_id']='version2'
    assert post(client,'/tickets/INC-1001/diagnostic-results',d)['version']==2
    b=resolution(evidence)
    done=post(client,'/tickets/INC-1001/resolution',b)
    assert done['status']=='RESOLVED' and done['closed_at'] is None
    assert done['resolved_at']==done['actual_finish_at']
    assert done['linked_solution_id']=='KB-001'
    assert post(client,'/tickets/INC-1001/resolution',b)==done
    post(client,'/tickets/INC-1001/worklogs',action(entry_type='NOTE',summary='late',rationale='late'),409)

@pytest.mark.parametrize('change',[{'user_confirmed_success':False},{'knowledge_article_id':'KB-002'},{'steps_completed':['wrong']},{'evidence_ids':[]},{'diagnosis_code':'ACCOUNT_LOCKED'}])
def test_resolution_guards(client,change):
    evidence=check(client)['evidence_id'];post(client,'/tickets/INC-1001/diagnostic-results',diagnosis(evidence_ids=[evidence]))
    before=get(client)
    post(client,'/tickets/INC-1001/resolution',resolution(evidence,**change),422)
    assert get(client)==before


def test_resolution_needs_recorded_diagnosis_and_real_tool_evidence(client):
    e=check(client)['evidence_id']
    post(client,'/tickets/INC-1001/resolution',resolution(e),422)
    fake=post(client,'/tickets/INC-1001/worklogs',action(entry_type='EVIDENCE',summary='claim',rationale='claim',evidence=[{'source_type':'USER_RESPONSE','source_id':'USR-001','observation':'password_expired=TRUE'}]))['evidence_ids'][0]
    post(client,'/tickets/INC-1001/diagnostic-results',diagnosis(evidence_ids=[fake]))
    post(client,'/tickets/INC-1001/resolution',resolution(fake),422)

@pytest.mark.parametrize('ticket',['INC-1009','INC-1010','INC-1011'])
def test_mandatory_human_review_and_approval(client,ticket):
    route=action(resolver_group_id='GRP-SEC',confidence='HIGH',reason='Specialist review')
    post(client,f'/tickets/{ticket}/assignment',route,422)
    r=post(client,f'/tickets/{ticket}/human-reviews',action(reason='Mandatory case',review_type='SAFETY',suggested_group_id='GRP-SEC'))
    assert r['state']=='REQUESTED' and get(client,ticket)['status']=='PENDING'
    post(client,f'/tickets/{ticket}/assignment',route,422)
    endpoint=f"/admin/human-reviews/{r['review_id']}/decision"
    decision=action(approved=True,reason='Human approved specialist routing')
    assert client.post(endpoint,json=decision).status_code==401
    approved=client.post(endpoint,json=decision,headers={'X-Admin-Key':'test-admin-key'})
    assert approved.status_code==200,approved.text
    assert client.post(endpoint,json=decision,headers={'X-Admin-Key':'test-admin-key'}).json()==approved.json()
    out=post(client,f'/tickets/{ticket}/assignment',route)
    assert out['assigned_group_id']=='GRP-SEC'
    post(client,f'/tickets/{ticket}/resolution',resolution('EV-MISSING'),422)

@pytest.mark.parametrize('confidence,status,triage',[('HIGH','QUEUED',False),('MEDIUM','QUEUED',False),('LOW','PENDING',True)])
def test_assignment_confidence(client,confidence,status,triage):
    b=action(resolver_group_id='GRP-APP',confidence=confidence,reason='App issue',alternative_resolver_group_ids=['GRP-IAM','GRP-END'])
    r=post(client,'/tickets/INC-1005/assignment',b)
    assert r['assigned_group_id']==('GRP-APP' if confidence=='HIGH' else 'GRP-L1')
    assert r['recommended_group_id']=='GRP-APP' and r['alternative_resolver_group_ids']==['GRP-IAM','GRP-END']
    assert r['status']==status and r['human_triage_required']==triage
    post(client,'/tickets/INC-1005/assignment',dict(b,action_id='bad',resolver_group_id='UNKNOWN'),404)


def test_notification_persistence(client,app):
    b=action(resolver_group_id='GRP-APP',severity='SEV3',message='Mock notification')
    out=post(client,'/tickets/INC-1005/notifications',b)
    assert out['delivery_mode']=='MOCK' and post(client,'/tickets/INC-1005/notifications',b)==out
    with app.state.sessions() as db: assert db.scalar(select(func.count()).select_from(m.Notification))==1


def test_all_outage_clusters_and_decoys(client):
    fixtures=json.loads((ROOT/'data/outage_fixtures.json').read_text())
    for scenario in fixtures['clusters']+fixtures['decoys']:
        b={k:scenario[k] for k in ('category','configuration_item_id','location_id','window_minutes')}
        result=post(client,'/tickets/count-recent',b)
        assert result['count']==scenario['expected_count']
        assert (result['count']>=scenario['minimum_count'])==scenario['name'].startswith('cluster')
        assert result['window_start']=='2026-10-01T11:30:00Z'
    post(client,'/tickets/count-recent',{},422)
    post(client,'/global-tickets/search',{},422)
    post(client,'/tickets/count-recent',{'category':'VPN','as_of':'2026-10-01T12:00:00'},422)


def test_global_create_link_duplicate_and_counts(client):
    assert post(client,'/global-tickets/search',{'category':'VPN'})=={'results':[]}
    b=global_body();first=post(client,'/global-tickets',b)
    assert not first['reused_existing'] and len(first['related_ticket_ids'])==2
    assert post(client,'/global-tickets',b)==first
    g=first['ticket_id']
    before=len(get(client,g)['worklogs'])
    again=post(client,'/global-tickets',dict(b,action_id='new-action'))
    assert again['reused_existing'] and again['ticket_id']==g
    assert len(get(client,g)['worklogs'])==before
    link=action(global_ticket_id=g,reason='Same outage')
    assert post(client,'/tickets/CLUSTER-1-3/global-link',link)['already_linked'] is False
    count_before=len(get(client,'CLUSTER-1-3')['worklogs'])
    assert post(client,'/tickets/CLUSTER-1-3/global-link',dict(link,action_id='repeat-link'))['already_linked']
    assert len(get(client,'CLUSTER-1-3')['worklogs'])==count_before
    assert post(client,'/tickets/count-recent',{'category':'VPN','configuration_item_id':'CI-VPN','location_id':'LOC-A'})['count']==0
    globals=post(client,'/global-tickets/search',{'category':'VPN','location_id':'LOC-A'})['results']
    assert len(globals)==1 and len(globals[0]['related_ticket_ids'])==3
    post(client,f'/tickets/{g}/global-link',action(global_ticket_id=g,reason='Self'),422)
    post(client,'/tickets/INC-1001/global-link',action(global_ticket_id='INC-1002',reason='Not global'),422)
    post(client,'/tickets/DECOY-1-1/global-link',action(global_ticket_id=g,reason='Wrong scope'),422)


def test_atomic_global_failure(client,app):
    before=get(client,'CLUSTER-1-1')
    post(client,'/global-tickets',global_body(related_ticket_ids=['CLUSTER-1-1','DECOY-1-1']),422)
    assert get(client,'CLUSTER-1-1')==before
    with app.state.sessions() as db: assert db.scalar(select(func.count()).select_from(m.Ticket).where(m.Ticket.is_global))==0


def test_transaction_rolls_back_late_failure(client):
    before=get(client)
    b=action(entry_type='EVIDENCE',summary='Several sources',rationale='Validation must be atomic',evidence=[{'source_type':'USER_RESPONSE','source_id':'USR-001','observation':'First valid'},{'source_type':'KNOWLEDGE_ARTICLE','source_id':'MISSING','observation':'Invalid'}])
    post(client,'/tickets/INC-1001/worklogs',b,404)
    assert get(client)==before


def test_ground_truth_excluded_and_historical_misroutes(client,app):
    with app.state.sessions() as db:
        tables=[row[0] for row in db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))]
        assert not any('truth' in t or 'scenario_answers' in t for t in tables)
        assert db.scalar(select(func.count()).select_from(m.Assignment))==6
    for i in range(1001,1013):
        response=get(client,f'INC-{i}')
        assert response['diagnosis_code'] is None and response['resolution_summary'] is None
        assert 'expected_diagnosis' not in json.dumps(response) and 'evaluation_only' not in json.dumps(response)


def test_sqlite_restart_persists_retry(client,app):
    b=action(summary='Persistent',description='Across restarts',reported_by_id='USR-001')
    created=post(client,'/tickets',b)
    second=create_app(app.state.settings)
    with TestClient(second,headers={'X-API-Key':'test-service-key'}) as c2:
        assert post(c2,'/tickets',b)==created
        assert get(c2,created['ticket_id'])==created
    second.state.engine.dispose()

@pytest.mark.parametrize('change',[{'outcome':'INCONCLUSIVE'},{'recommended_action':'RESOLVE','confidence':'LOW'},{'outcome':'HUMAN_REQUIRED'},{'diagnosis_code':'NOT-A-DIAGNOSIS'},{'evidence_ids':['EV-MISSING']}])
def test_diagnostic_invalid_consistency(client,change):
    b=diagnosis();b.update(change)
    response=client.post('/tickets/INC-1001/diagnostic-results',json=b)
    assert response.status_code in (404,422)
    assert get(client)['diagnosis_code'] is None


def test_inconclusive_arabic_workflow(client):
    b=diagnosis();b.update(diagnosis_code=None,outcome='INCONCLUSIVE',candidate_diagnoses=[],confidence='LOW',recommended_action='ASK_MORE',missing_information=['ما هو التطبيق؟'],rationale='نحتاج معلومات إضافية')
    result=post(client,'/tickets/INC-1012/diagnostic-results',b)
    assert result['diagnosis_code'] is None
    assert post(client,'/tickets/INC-1012/human-reviews',action(reason='Insufficient evidence',review_type='INVESTIGATION',suggested_group_id='GRP-L1'))['state']=='REQUESTED'


@pytest.mark.parametrize('path,body',[
('/tickets/MISSING/assignment',{'resolver_group_id':'GRP-L1','confidence':'LOW','reason':'x'}),
('/tickets/MISSING/worklogs',{'entry_type':'NOTE','summary':'x','rationale':'x'}),
('/tickets/MISSING/resolution',{'diagnosis_code':'PASSWORD_EXPIRED','resolution_summary':'x','steps_completed':['PASSWORD_EXPIRED-1'],'knowledge_article_id':'KB-001','user_confirmed_success':True}),
('/tickets/MISSING/global-link',{'global_ticket_id':'INC-1001','reason':'x'}),
('/tickets/MISSING/human-reviews',{'reason':'x','review_type':'TRIAGE','suggested_group_id':'GRP-L1'}),
('/tickets/MISSING/notifications',{'resolver_group_id':'GRP-L1','severity':'SEV3','message':'x'}),
('/diagnostics/application-entitlement',{'ticket_id':'MISSING','user_id':'USR-001','application_id':'APP-PORTAL'}),
('/diagnostics/service-health',{'ticket_id':'MISSING','configuration_item_id':'CI-PORTAL'}),
])
def test_unknown_mutation_ticket_ids(client,path,body):
    post(client,path,action(**body),404)


def test_mandatory_resolution_cannot_use_approval(client):
    created=post(client,'/tickets',action(summary='Sensitive access issue',description='User reported access issue',reported_by_id='USR-001',security_sensitive=True))
    t=created['ticket_id'];e=check(client,t)['evidence_id']
    d=diagnosis(evidence_ids=[e]);d['recommended_action']='ESCALATE'
    post(client,f'/tickets/{t}/diagnostic-results',d)
    error=post(client,f'/tickets/{t}/resolution',resolution(e),422)
    assert error['code']=='HUMAN_REVIEW_REQUIRED'


def test_safety_flags_added_and_preserved(client):
    b=diagnosis();b.update(diagnosis_code='PHISHING',recommended_action='ESCALATE',candidate_diagnoses=[])
    post(client,'/tickets/INC-1001/diagnostic-results',b)
    assert get(client)['security_sensitive']
    b=diagnosis();b['recommended_action']='ESCALATE'
    post(client,'/tickets/INC-1001/diagnostic-results',b)
    assert get(client)['security_sensitive']


def test_cross_ticket_and_future_evidence_rejected(client):
    e=check(client)['evidence_id']
    post(client,'/tickets/INC-1002/worklogs',action(entry_type='NOTE',summary='x',rationale='x',evidence_ids=[e]),422)
    post(client,'/tickets/INC-1001/worklogs',action(entry_type='EVIDENCE',summary='x',rationale='x',evidence=[{'source_type':'USER_RESPONSE','source_id':'USR-001','observation':'future','observed_at':'2030-01-01T00:00:00Z'}]),422)


def test_inactive_globals_excluded_and_cannot_link(client,app):
    g=post(client,'/global-tickets',global_body())['ticket_id']
    with app.state.sessions() as db:
        global_ticket=db.get(m.Ticket,g);global_ticket.status='RESOLVED';global_ticket.active_scope=None;db.commit()
    assert post(client,'/global-tickets/search',{'category':'VPN'})['results']==[]
    post(client,'/tickets/CLUSTER-1-3/global-link',action(global_ticket_id=g,reason='Inactive'),409)


def test_count_utc_boundary_and_and_filters(client):
    b={'category':'VPN','configuration_item_id':'CI-VPN','location_id':'LOC-A','window_minutes':30,'as_of':'2026-10-01T15:00:00+03:00'}
    assert post(client,'/tickets/count-recent',b)['count']==3
    b['as_of']='2026-10-01T12:00:00.000001Z'
    assert post(client,'/tickets/count-recent',b)['count']==2
    b['location_id']='LOC-B'
    assert post(client,'/tickets/count-recent',b)['count']==0


def test_concurrent_global_creation_serialized(app):
    from concurrent.futures import ThreadPoolExecutor
    def create_one(index):
        with TestClient(app,headers={'X-API-Key':'test-service-key'}) as client:
            return post(client,'/global-tickets',global_body(action_id=f'concurrent-{index}'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(create_one,range(2)))
    assert results[0]['ticket_id']==results[1]['ticket_id']
    assert sorted(r['reused_existing'] for r in results)==[False,True]


def test_conflicting_global_relationship(client,app):
    g=post(client,'/global-tickets',global_body(related_ticket_ids=['CLUSTER-1-1']))['ticket_id']
    # Simulate a preexisting active issue with a different legacy scope key.
    with app.state.sessions() as db:
        original=db.get(m.Ticket,g)
        fields={c.name:getattr(original,c.name) for c in m.Ticket.__table__.columns}
        fields.update(ticket_id='GLB-LEGACY',active_scope='legacy-scope')
        db.add(m.Ticket(**fields));db.commit()
    post(client,'/tickets/CLUSTER-1-1/global-link',action(global_ticket_id='GLB-LEGACY',reason='Conflict'),409)
    assert get(client,'CLUSTER-1-1')['global_ticket_id']==g

def test_four_demonstration_flows(client):
    from scripts.demo_flows import run_flows
    result=run_flows(client)
    assert result['resolved_ticket']=='INC-1001' and result['specialist_group']=='GRP-APP'

def test_global_diagnosis_cannot_break_scope(client):
    g=post(client,'/global-tickets',global_body())['ticket_id']
    for t in (g,'CLUSTER-1-1'):
        b=diagnosis();b['recommended_action']='ROUTE'
        post(client,f'/tickets/{t}/diagnostic-results',b,422)
        assert get(client,t)['category']=='VPN'


def test_critical_global_requires_human_owner(client):
    post(client,'/global-tickets',global_body(severity='SEV1'),422)
    result=post(client,'/global-tickets',global_body(severity='SEV1',owner_group_id='GRP-L1'))
    assert get(client,result['ticket_id'])['reported_priority']==1

def test_quoted_and_natural_secret_redaction(client):
    text='password is "two word secret"; token was abc123; secret=xyz987'
    post(client,'/tickets/INC-1001/worklogs',action(entry_type='NOTE',summary=text,rationale=text))
    result=json.dumps(get(client))
    for secret in ('two word secret','abc123','xyz987'): assert secret not in result

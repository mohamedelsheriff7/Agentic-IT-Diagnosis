"""Integration checks for the independently supplied Workstream A dataset."""
import json
import shutil
from copy import deepcopy
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func,text
from app.config import ROOT,Settings
from app.main import create_app
from app.importer import import_dataset
from app.models import database,Ticket,Reference
from app.evaluation_contract import EvaluationRecord
from scripts.merge_workstream_a import validate_pair

DATA=ROOT/'data/workstream_a'
EVALUATION=ROOT/'evaluation/workstream_a'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

@pytest.fixture(scope='module')
def a_template(tmp_path_factory):
    path=tmp_path_factory.mktemp('workstream-a')/'template.db'
    engine,sessions=database('sqlite:///'+str(path))
    with sessions() as db:
        assert import_dataset(db,DATA)==634;db.commit()
    engine.dispose()
    return path

@pytest.fixture
def a_app(tmp_path,a_template):
    path=tmp_path/'test.db';shutil.copyfile(a_template,path)
    app=create_app(Settings(database_url='sqlite:///'+str(path),api_key='test-service-key',admin_api_key='test-admin-key'))
    yield app
    app.state.engine.dispose()

@pytest.fixture
def a_client(a_app):
    with TestClient(a_app,headers={'X-API-Key':'test-service-key'}) as client:yield client

def post(client,path,body):
    result=client.post(path,json=body)
    assert result.status_code==200,result.text
    return result.json()

def test_a_schema_joins_and_ids(a_app):
    labels=read(EVALUATION/'ground_truth.json')
    tickets=read(DATA/'sample_open_tickets.json')
    taxonomy={r['diagnosis_code']:r for r in read(DATA/'taxonomy.json')}
    groups={r['id'] for r in read(DATA/'resolver_groups.json')}
    facts=validate_pair(tickets,labels,taxonomy,groups)
    assert len(labels)==len(tickets)==134 and len(facts)==96
    with a_app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Ticket))==634
        assert db.get(Reference,'ACCOUNT_LOCKED_POLICY').data['security_sensitive'] is True
        assert db.get(Reference,'VPN_CLIENT_ISSUE').data['resolver_group_id']=='GRP-NET'

def test_a_all_tickets_hide_labels(a_client,a_app):
    for row in read(EVALUATION/'ground_truth.json'):
        result=a_client.get('/tickets/'+row['ticket_id'])
        assert result.status_code==200
        ticket=result.json()
        assert ticket['diagnosis_code'] is None and ticket['latest_diagnostic_result'] is None
        assert ticket['linked_solution_id'] is None and ticket['resolution_summary'] is None
        assert not set(row).difference({'ticket_id'}) & set(ticket)
        assert all('expected_' not in json.dumps(w) and 'discoverable_information' not in json.dumps(w) for w in ticket['worklogs'])
    for url in ['/evaluation/workstream_a/ground_truth.json','/data/workstream_a/ground_truth.json','/ground_truth.json']:
        assert a_client.get(url).status_code==404
    with a_app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Ticket).where(Ticket.ticket_id.like('CLUSTER-%')))==0
        assert db.scalar(select(func.count()).select_from(Ticket).where(Ticket.ticket_id.like('INC-%')))==0
        assert not any('truth' in r[0] for r in db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")))

def test_a_every_declared_fixture_reads_exactly(a_client):
    tickets={r['ticket_id']:r for r in read(DATA/'sample_open_tickets.json')}
    count=0
    for label in read(EVALUATION/'ground_truth.json'):
        ticket=tickets[label['ticket_id']]
        for tool,expected in label['required_fixtures'].items():
            body=dict(ticket_id=ticket['ticket_id'],action_id='verify-'+ticket['ticket_id']+'-'+tool)
            if tool=='check_account_status':
                body['user_id']=ticket['affected_person_id'];path='/diagnostics/account-status'
            elif tool=='check_application_entitlement':
                body.update(user_id=ticket['affected_person_id'],application_id=expected['application_id']);path='/diagnostics/application-entitlement'
            else:
                body.update(configuration_item_id=expected['configuration_item_id'],location_id=expected.get('location_id'));path='/diagnostics/service-health'
            result=post(a_client,path,body)
            assert all(result[k]==v for k,v in expected.items())
            assert result['evidence_id']
            assert post(a_client,path,body)==result
            count+=1
    assert count>96  # Some scopes are intentionally shared by several tickets.

@pytest.mark.parametrize('cluster_id',['OUT-1','OUT-2','OUT-3'])
def test_a_outage_arrival_create_then_link(a_client,cluster_id):
    tickets={r['ticket_id']:r for r in read(DATA/'sample_open_tickets.json')}
    labels=sorted([r for r in read(EVALUATION/'ground_truth.json') if r['cluster_id']==cluster_id],key=lambda r:r['cluster_position'])
    seen=[];global_id=None
    for label in labels:
        ticket=tickets[label['ticket_id']];seen.append(ticket['ticket_id'])
        scope={k:ticket[k] for k in ('category','configuration_item_id','location_id')}
        if label['cluster_position']<3:
            result=post(a_client,'/tickets/count-recent',dict(scope,window_minutes=30,as_of=ticket['reported_at']))
            assert result['count']==label['cluster_position']
            assert label['expected_outage_action']=='none'
        elif label['cluster_position']==3:
            result=post(a_client,'/tickets/count-recent',dict(scope,window_minutes=30,as_of=ticket['reported_at']))
            assert result['count']==3
            issue=post(a_client,'/global-tickets',dict(scope,action_id='global-'+cluster_id,summary='Independent service outage observation',description='Affected synthetic scope',severity='SEV2',owner_group_id=label['expected_resolver_group_id'],related_ticket_ids=seen,reason='Third arrival reaches the declared threshold.'))
            global_id=issue['ticket_id'];assert label['expected_outage_action']=='create_global'
        else:
            found=post(a_client,'/global-tickets/search',scope)
            assert found['results'][0]['ticket_id']==global_id
            post(a_client,'/tickets/'+ticket['ticket_id']+'/global-link',dict(action_id='link-'+ticket['ticket_id'],global_ticket_id=global_id,reason='Later arrival in the same issue scope.'))
            assert label['expected_outage_action']=='link_existing'
    assert len(a_client.get('/tickets/'+global_id).json()['related_ticket_ids'])==8

@pytest.mark.parametrize('cluster_id,maximum',[('DECOY-1',1),('DECOY-2',2),('DECOY-3',1)])
def test_a_decoys_never_reach_three(a_client,cluster_id,maximum):
    tickets={r['ticket_id']:r for r in read(DATA/'sample_open_tickets.json')}
    labels=[r for r in read(EVALUATION/'ground_truth.json') if r['cluster_id']==cluster_id]
    counts=[]
    for label in labels:
        ticket=tickets[label['ticket_id']]
        result=post(a_client,'/tickets/count-recent',dict(category=ticket['category'],configuration_item_id=ticket['configuration_item_id'],location_id=ticket['location_id'],window_minutes=30,as_of=ticket['reported_at']))
        counts.append(result['count'])
        assert label['expected_outage_action']=='none' and result['count']<3
    assert max(counts)==maximum

@pytest.mark.parametrize('diagnosis_code',['ACCOUNT_LOCKED_POLICY','VPN_CLIENT_ISSUE'])
def test_a_distinct_codes_survive_history_and_diagnosis(a_client,diagnosis_code):
    historical=[t for t in read(DATA/'historical_tickets.json') if t['diagnosis_code']==diagnosis_code]
    assert historical
    assert a_client.get('/tickets/'+historical[0]['ticket_id']).json()['diagnosis_code']==diagnosis_code
    label=next(r for r in read(EVALUATION/'ground_truth.json') if r['expected_diagnosis_code']==diagnosis_code)
    result=post(a_client,'/tickets/'+label['ticket_id']+'/diagnostic-results',dict(action_id='distinct-'+diagnosis_code,diagnosis_code=diagnosis_code,outcome='DIAGNOSED',confidence='HIGH',confidence_basis=dict(knowledge_match_strength='MEDIUM',evidence_completeness='HIGH',historical_agreement='AGREES',alternatives_excluded=True),recommended_action='ESCALATE' if label['human_required'] else 'ROUTE',rationale='Test harness supplied conclusion after synthetic evidence.'))
    assert result['diagnosis_code']==diagnosis_code
    if diagnosis_code=='ACCOUNT_LOCKED_POLICY':assert a_client.get('/tickets/'+label['ticket_id']).json()['security_sensitive']

def test_a_all_six_password_resolution_labels_are_supported(a_client):
    tickets={r['ticket_id']:r for r in read(DATA/'sample_open_tickets.json')}
    labels=[r for r in read(EVALUATION/'ground_truth.json') if r['agent_resolvable']]
    assert len(labels)==6
    for label in labels:
        ticket=tickets[label['ticket_id']]
        evidence=post(a_client,'/diagnostics/account-status',dict(action_id='account-'+ticket['ticket_id'],ticket_id=ticket['ticket_id'],user_id=ticket['affected_person_id']))['evidence_id']
        post(a_client,'/tickets/'+ticket['ticket_id']+'/diagnostic-results',dict(action_id='diagnose-'+ticket['ticket_id'],diagnosis_code=label['expected_diagnosis_code'],outcome='DIAGNOSED',confidence='HIGH',confidence_basis=dict(knowledge_match_strength='HIGH',evidence_completeness='HIGH',historical_agreement='AGREES',alternatives_excluded=True),recommended_action='RESOLVE',evidence_ids=[evidence],knowledge_article_ids=['KB-001'],rationale='Test harness confirms the declared observations.'))
        result=post(a_client,'/tickets/'+ticket['ticket_id']+'/resolution',dict(action_id='resolve-'+ticket['ticket_id'],diagnosis_code='PASSWORD_EXPIRED',resolution_summary='Synthetic user confirmed successful self-service change.',steps_completed=['PASSWORD_EXPIRED-1'],knowledge_article_id='KB-001',user_confirmed_success=True,evidence_ids=[evidence]))
        assert result['status']=='RESOLVED'

def test_a_rejects_conflicting_static_fixtures():
    tickets=read(DATA/'sample_open_tickets.json');labels=deepcopy(read(EVALUATION/'ground_truth.json'))
    health_labels=[r for r in labels if r['required_fixtures'].get('check_service_health',{}).get('configuration_item_id')=='CI-VPN' and r['required_fixtures']['check_service_health'].get('location_id')=='LOC-A']
    assert len(health_labels)>1
    health_labels[0]['required_fixtures']['check_service_health']['state']='OPERATIONAL'
    with pytest.raises(ValueError,match='Conflicting stored fixture'):
        validate_pair(tickets,labels,{r['diagnosis_code']:r for r in read(DATA/'taxonomy.json')},{r['id'] for r in read(DATA/'resolver_groups.json')})

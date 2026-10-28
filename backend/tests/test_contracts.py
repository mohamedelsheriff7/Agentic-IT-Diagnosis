import json
import re
import shutil
import pytest
from sqlalchemy import select,func
from openapi_spec_validator import validate
from app.config import ROOT
from app.importer import import_dataset,read_dataset
from app import models as m
from scripts.export_openapi import export_specs,convert,public_url
from scripts.generate_fixtures import generate

EXPECTED=set('get_ticket_details search_similar_tickets assign_ticket add_worklog_entry resolve_ticket count_recent_tickets find_open_global_tickets create_global_ticket link_ticket_to_global_ticket check_account_status check_application_entitlement check_service_health create_ticket request_human_review notify_resolver_group search_diagnostic_knowledge record_diagnostic_result'.split())

def test_openapi_contract(app):
    full,agent=export_specs(app,'https://test.example.com')
    validate(agent)
    ops=[op for methods in agent['paths'].values() for op in methods.values()]
    assert {op['operationId'] for op in ops}==EXPECTED
    assert len(ops)==17 and agent['servers']==[{'url':'https://test.example.com'}]
    assert agent['openapi']=='3.0.3'
    assert all(re.fullmatch('[a-z_]+',op['operationId']) for op in ops)
    assert all(op['security']==[{'ServiceApiKey':[]}] for op in ops)
    assert agent['components']['securitySchemes']['ServiceApiKey']=={'type':'apiKey','in':'header','name':'X-API-Key'}
    assert '/health' in full['paths'] and '/health' not in agent['paths']
    assert not any(p.startswith('/admin') for p in agent['paths'])
    assert 'ReviewDecision' not in agent['components']['schemas']
    raw=json.dumps(agent)
    assert '"type": "null"' not in raw and '"const"' not in raw and 'localhost' not in raw
    for op in ops:
        assert op['summary'] and op['description']
        for code in ('401','404','409','422'): assert code in op['responses']
        assert op['responses']['200']['content']['application/json']['schema']

@pytest.mark.parametrize('url',['http://example.com','https://localhost','https://127.0.0.1','https://10.0.0.1','https://[::1]','https://host.local','https://{tenant}.example.com','https://user:pass@example.com','https://example.com?key=x',''])
def test_export_rejects_bad_servers(url):
    with pytest.raises(ValueError): public_url(url)


def test_real_schema_conversion():
    schema=convert({'anyOf':[{'type':'string'},{'type':'null'}],'examples':['a'],'const':'a','exclusiveMinimum':1})
    assert schema['nullable'] and schema['type']=='string' and schema['enum']==['a'] and schema['example']=='a'
    assert schema['minimum']==1 and schema['exclusiveMinimum'] is True
    with pytest.raises(ValueError): convert({'prefixItems':[]})


def test_fixture_generation_reproducible(tmp_path):
    generate(tmp_path/'one');generate(tmp_path/'two')
    for p in (tmp_path/'one').rglob('*.json'):
        assert p.read_bytes()==(tmp_path/'two'/p.relative_to(tmp_path/'one')).read_bytes()
    generate(tmp_path/'three',clock='2027-01-01T00:00:00Z')
    assert (tmp_path/'one/data/sample_open_tickets.json').read_bytes()!=(tmp_path/'three/data/sample_open_tickets.json').read_bytes()


def test_import_reset_is_atomic(app,tmp_path,starter_data):
    data=tmp_path/'data';shutil.copytree(starter_data,data)
    tickets=json.loads((data/'sample_open_tickets.json').read_text(encoding='utf-8'))
    tickets[-1]['reported_by_id']='MISSING'
    (data/'sample_open_tickets.json').write_text(json.dumps(tickets),encoding='utf-8')
    with app.state.sessions() as db:
        with pytest.raises(Exception):
            try: import_dataset(db,data,reset=True);db.commit()
            except Exception: db.rollback();raise
        assert db.scalar(select(func.count()).select_from(m.Ticket))==70
        assert db.get(m.Ticket,'INC-1001') is not None


def test_import_rejects_hidden_fields(tmp_path,starter_data):
    data=tmp_path/'data';shutil.copytree(starter_data,data)
    tickets=json.loads((data/'sample_open_tickets.json').read_text(encoding='utf-8'))
    tickets[0]['expected_diagnosis']='PASSWORD_EXPIRED'
    (data/'sample_open_tickets.json').write_text(json.dumps(tickets),encoding='utf-8')
    with pytest.raises(ValueError): read_dataset(data)


def test_large_dataset_validation(tmp_path,starter_data):
    data=tmp_path/'data';shutil.copytree(starter_data,data)
    for filename,count in [('historical_tickets',500),('sample_open_tickets',90)]:
        source=json.loads((data/(filename+'.json')).read_text(encoding='utf-8'))
        rows=[dict(source[i%len(source)],ticket_id=f'{filename}-{i}') for i in range(count)]
        (data/(filename+'.json')).write_text(json.dumps(rows),encoding='utf-8')
    engine,sessions=m.database('sqlite:///'+str(tmp_path/'large.db'))
    with sessions() as db:
        assert import_dataset(db,data)==590;db.commit()
    engine.dispose()

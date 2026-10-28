import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
import server

@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('DIAGNOSTIC_SERVICE_API_KEY', 'test-service-key')
    monkeypatch.setenv('DIAGNOSTIC_SESSIONS_DIR', str(tmp_path))
    monkeypatch.delenv('DIAGNOSTIC_BACKEND_API_KEY', raising=False)
    return TestClient(server.app, headers={'X-API-Key': 'test-service-key'})

def test_auth_and_configuration(api):
    assert api.get('/health').json()['status'] == 'ok'
    assert api.get('/investigations/missing', headers={'X-API-Key': 'bad'}).status_code == 401
    assert api.post('/investigations', json={'mode': 'backend', 'ticket_id': 'T-1'}).status_code == 503
    schema = api.get('/openapi.json').json()
    assert schema['components']['securitySchemes']['APIKeyHeader']['name'] == 'X-API-Key'

def test_local_multiturn_and_persistence(api):
    ticket = {'ticket_id': 'API-1', 'summary': 'Cannot sign in', 'description': 'Portal access denied'}
    first = api.post('/investigations', json={'ticket_id': 'API-1', 'ticket': ticket})
    assert first.status_code == 200, first.text
    assert first.json()['next_question']
    reply = api.post('/investigations/API-1/answers', json={'answer': 'Unknown, error code 512', 'evidence_id': 'ANSWER-1'})
    assert reply.status_code == 200, reply.text
    trace = api.get('/investigations/API-1').json()['state']
    assert trace['evidence'][-1]['value'] == 'Unknown, error code 512'
    assert trace['status'] != 'resolved'
    assert api.get('/investigations/missing').status_code == 404

@pytest.mark.parametrize('flags', [{'priority': '1'}, {'security_sensitive': True}, {'privileged_access': True}])
def test_human_handling(api, flags):
    ticket = {'ticket_id': 'SAFE-1', 'summary': 'Access issue', 'description': 'Cannot sign in', **flags}
    result = api.post('/investigations', json={'ticket_id': 'SAFE-1', 'ticket': ticket}).json()
    assert result['recommended_action'] == 'ESCALATE'
    assert result['completed_actions'] == []

def test_backend_resolution_failure_never_claims_success(tmp_path, monkeypatch):
    from diagnostic_agent import integrated
    from diagnostic_agent.models import DiagnosticState, TicketInput, DiagnosisCandidate
    from diagnostic_agent.session_store import JsonSessionStore
    from diagnostic_agent.backend_client import BackendRequestError
    store = JsonSessionStore(tmp_path)
    state = DiagnosticState(ticket=TicketInput('RES-1', 'Expired', 'Password expired'),
        status='diagnosed', final_diagnosis='PASSWORD_EXPIRED',
        candidates=[DiagnosisCandidate('PASSWORD_EXPIRED', 'Expired', 'Access', 'Auth', 'IAM',
            status='confirmed', knowledge_article_id='KB-001')])
    store.save(state)
    monkeypatch.setattr(integrated, 'start_resolution', lambda *a, **k: {'article_id': 'KB-001', 'steps': [{'step_id': 'S1'}]})
    class RejectingBackend:
        def get_ticket_details(self, tid):
            return {'ticket_id': tid, 'summary': 'Expired', 'description': 'Expired', 'reported_priority': 3}
        def resolve_ticket(self, *a):
            raise BackendRequestError('Rejected', status=409)
    with pytest.raises(BackendRequestError):
        integrated.confirm_resolution_and_close(RejectingBackend(), 'RES-1', True, ['S1'], store)
    assert store.load('RES-1').status == 'diagnosed'

def test_arabic_retrieval(tmp_path):
    import json
    from diagnostic_agent.knowledge import search_articles
    path = tmp_path / 'articles.json'
    path.write_text(json.dumps([{'article_id': 'AR-1', 'approved': True, 'symptoms_ar': ['كلمة المرور انتهت صلاحيتها']}]), encoding='utf-8')
    assert search_articles('كلمة المرور انتهت', path=path)[0]['article_id'] == 'AR-1'

def test_backend_answer_uses_affected_person_and_persisted_evidence(tmp_path, monkeypatch):
    from diagnostic_agent import integrated
    from diagnostic_agent.engine import start_investigation
    from diagnostic_agent.models import TicketInput
    from diagnostic_agent.session_store import JsonSessionStore
    store = JsonSessionStore(tmp_path)
    state = start_investigation(TicketInput('ANS-1', 'Cannot sign in', 'Portal access denied'))
    store.save(state)
    class Backend:
        def get_ticket_details(self, tid):
            return {'status': 'IN_PROGRESS', 'affected_person_id': 'PERSON-1'}
        def add_worklog_entry(self, tid, payload):
            assert payload['evidence'][0]['source_id'] == 'PERSON-1'
            assert payload['evidence'][0]['source_type'] == 'USER_RESPONSE'
            assert payload['summary'].startswith('[DiagnosticAgent]')
            return {'evidence_ids': ['BACKEND-EVIDENCE-1']}
    monkeypatch.setattr(integrated, 'investigate_ticket', lambda *a, **kw: {'continued': True})
    integrated.submit_answer_and_continue(Backend(), 'ANS-1', 'Unknown error 512', 'CLIENT-ANSWER-1', store)
    assert store.load('ANS-1').evidence[-1].evidence_id == 'BACKEND-EVIDENCE-1'

def test_other_app_access_does_not_eliminate_account_diagnoses():
    from diagnostic_agent.engine import _map_answer_to_diagnoses
    supports, contradicts = _map_answer_to_diagnoses('Can you access other corporate applications?', 'yes')
    assert 'MISSING_ENTITLEMENT' in supports
    assert not {'PASSWORD_EXPIRED', 'ACCOUNT_LOCKED'}.intersection(contradicts)

def test_secrets_redacted_but_exact_ids_preserved(api):
    tid = 'TICKET-' + 'a' * 32
    result = api.post('/investigations', json={'ticket_id': tid, 'ticket': {
        'ticket_id': tid, 'summary': 'Access issue', 'description': 'password=FakeSecret123 cannot sign in'}})
    assert result.status_code == 200
    trace = api.get('/investigations/' + tid)
    assert 'FakeSecret123' not in trace.text
    assert trace.json()['state']['ticket']['ticket_id'] == tid

def test_local_langgraph_http_checkpoint(api):
    import json
    ticket = {'ticket_id': 'GRAPH-API-1', 'summary': 'Cannot sign in', 'description': 'Portal access denied'}
    first = api.post('/langgraph/chat', json={'session_id': 'graph-api-session', 'mode': 'local',
        'message': json.dumps({'ticket_id': 'GRAPH-API-1', 'ticket': ticket})})
    assert first.status_code == 200, first.text
    assert first.json()['framework'] == 'langgraph'
    assert not first.json()['reply'].startswith('{')
    second = api.post('/langgraph/chat', json={'session_id': 'graph-api-session', 'mode': 'local',
        'message': 'Unknown error 512'})
    assert second.status_code == 200, second.text
    assert second.json()['diagnostic_session']['snapshot']['evidence'][-1]['value'] == 'Unknown error 512'

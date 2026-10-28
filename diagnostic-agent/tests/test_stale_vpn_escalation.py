import json
from pathlib import Path
from diagnostic_agent.engine import add_evidence
from diagnostic_agent.models import Evidence, DiagnosisCandidate
from diagnostic_agent.session_store import JsonSessionStore, _state_from_dict
from diagnostic_agent.integrated import investigate_ticket
from test_backend_integration import FakeBackend

def snapshot():
    return json.loads((Path(__file__).parent / 'fixtures' / 'stale_vpn_session.json').read_text(encoding='utf-8'))

def test_new_evidence_clears_only_superseded_outage_escalation():
    data = snapshot()
    data['evidence'] = []
    data['eliminated_diagnoses'] = []
    state = _state_from_dict(data)
    state.candidates.append(DiagnosisCandidate('VPN_OUTAGE', 'VPN outage', 'Network', 'VPN', 'GRP-NET'))
    add_evidence(state, Evidence('NEW-HEALTH', 'VPN health is operational', {'state': 'OPERATIONAL'},
        'diagnostic_check', contradicts=['VPN_OUTAGE']))
    assert state.status == 'in_progress'
    assert state.recommended_action == 'investigate'
    assert state.next_question
    assert any(step.event_type == 'outage_signal_cleared' for step in state.trace)

def test_actual_wxo_snapshot_resumes_without_stale_handoff(tmp_path):
    data = snapshot()
    state = _state_from_dict(data)
    store = JsonSessionStore(tmp_path)
    store.save(state)
    raw = dict(data['ticket'], reported_priority=3, status='NEW', affected_person_id='PERSON-TEST')
    client = FakeBackend(raw)
    response = investigate_ticket(client, state.ticket.ticket_id, store=store)
    assert response['recommended_action'] == 'ASK_MORE'
    assert response['next_question'] == 'Can colleagues at the same site connect to VPN right now?'
    assert response['outcome'] == 'INCONCLUSIVE'
    assert response['confidence_basis']['historical_agreement'] == 'NOT_AVAILABLE'
    assert response['confidence_basis']['historical_counts']['matching'] is None
    checkpoint = next(payload for name, payload in client.calls if name == 'record_diagnostic_result')
    assert checkpoint['confidence_basis']['historical_agreement'] == 'NOT_AVAILABLE'
    assert 'VPN_OUTAGE' not in response['remaining_candidates']

def test_outage_reassessment_cannot_clear_mandatory_human_case():
    from diagnostic_agent.engine import _check_outage_signal
    data = snapshot()
    data['ticket']['security_sensitive'] = True
    state = _state_from_dict(data)
    _check_outage_signal(state)
    assert state.status == 'escalated'

def test_trace_enums_are_not_redacted_but_secrets_are():
    from wxo_langgraph.agent import sanitize
    result = sanitize({'event_type': 'historical_tickets_retrieved', 'description': 'password=FakeSecret123'})
    assert result['event_type'] == 'historical_tickets_retrieved'
    assert 'FakeSecret123' not in result['description']

import json
from pathlib import Path
from diagnostic_agent.engine import submit_answer, add_evidence
from diagnostic_agent.models import Evidence
from diagnostic_agent.session_store import _state_from_dict, JsonSessionStore
from diagnostic_agent.integrated import investigate_ticket
from test_backend_integration import FakeBackend

QUESTION = 'Can colleagues at the same site connect to VPN right now?'

def before_answer():
    data = json.loads((Path(__file__).parent / 'fixtures' / 'stale_vpn_session.json').read_text(encoding='utf-8'))
    state = _state_from_dict(data)
    state.status = 'in_progress'
    state.recommended_action = 'investigate'
    state.next_question = QUESTION
    state.questions_asked = [QUESTION]
    return state

def test_no_reopens_shared_hypothesis_and_preserves_conflicting_monitor():
    state = before_answer()
    submit_answer(state, 'no', 'ANSWER-NO')
    outage = next(c for c in state.candidates if c.diagnosis_id == 'VPN_OUTAGE')
    assert outage.status == 'plausible'
    assert outage.supporting_evidence_ids == ['ANSWER-NO']
    assert outage.contradicting_evidence_ids == ['EV-a54e96f85bb44132']
    assert state.final_diagnosis is None
    assert state.status == 'escalated'
    assert state.next_question is None
    assert 'Current evidence conflicts' in state.rationale
    assert 'Supervisor' in state.rationale
    assert 'VPN_OUTAGE' not in {e['diagnosis_id'] for e in state.eliminated_diagnoses}
    assert any(t.event_type == 'hypothesis_reopened' for t in state.trace)

def test_yes_continues_individual_diagnosis_without_inventing_outage():
    state = before_answer()
    submit_answer(state, 'yes', 'ANSWER-YES')
    assert state.final_diagnosis is None
    assert state.status == 'in_progress'
    assert state.next_question == 'Does the VPN client show a local configuration or credential error?'
    assert 'VPN_OUTAGE' not in {c.diagnosis_id for c in state.candidates}

def test_unknown_does_not_reopen_or_confirm_any_diagnosis():
    state = before_answer()
    submit_answer(state, 'I do not know', 'ANSWER-UNKNOWN')
    assert state.final_diagnosis is None
    assert state.evidence[-1].supports == []
    assert state.evidence[-1].contradicts == []
    assert 'VPN_OUTAGE' not in {c.diagnosis_id for c in state.candidates}

class OutageBackend(FakeBackend):
    def find_open_global_tickets(self, payload):
        self.calls.append(('find_open_global_tickets', payload))
        return {'results': []}
    def count_recent_tickets(self, payload):
        self.calls.append(('count_recent_tickets', payload))
        return {'count': 1, 'matching_ticket_ids': ['TST-0001']}

def test_actual_after_no_snapshot_recovers_and_screens_outage(tmp_path):
    data = json.loads((Path(__file__).parent / 'fixtures' / 'vpn_after_no_v3.json').read_text(encoding='utf-8'))
    state = _state_from_dict(data)
    store = JsonSessionStore(tmp_path)
    store.save(state)
    client = OutageBackend(dict(data['ticket'], status='NEW', reported_priority=3))
    response = investigate_ticket(client, 'TST-0001', store=store)
    assert response['recommended_action'] == 'ESCALATE'
    assert response['outcome'] == 'HUMAN_REQUIRED'
    assert response['remaining_candidates'] == ['VPN_OUTAGE']
    assert response['evidence_conflicts'][0]['supporting_evidence_ids'] == ['EV-aa8702248c984b34']
    assert response['evidence_conflicts'][0]['contradicting_evidence_ids'] == ['EV-08c47d0ad4b24869']
    assert 'Current evidence conflicts' in response['rationale']
    assert any(name == 'find_open_global_tickets' for name, _ in client.calls)
    assert any(name == 'count_recent_tickets' for name, _ in client.calls)
    checkpoint = next(p for name, p in client.calls if name == 'record_diagnostic_result')
    assert not ({d['diagnosis_code'] for d in checkpoint['candidate_diagnoses']} &
                {d['diagnosis_code'] for d in checkpoint['eliminated_diagnoses']})
    assert response['completed_actions'] == []
    assert response['next_question'] is None
    assert QUESTION not in response['missing_information']
    assert 'Scoped backend screening: 1 recent matching ticket(s)' in response['rationale']
    assert not any(a.event_type == b.event_type == 'outage_signal_detected' and a.description == b.description
        for a, b in zip(store.load('TST-0001').trace, store.load('TST-0001').trace[1:]))

def test_zero_recent_tickets_does_not_confirm_or_automate_an_outage(tmp_path):
    state = before_answer()
    submit_answer(state, 'no', 'ANSWER-NO')
    store = JsonSessionStore(tmp_path)
    store.save(state)
    class ZeroBackend(OutageBackend):
        def count_recent_tickets(self, payload):
            return {'count': 0, 'matching_ticket_ids': []}
    client = ZeroBackend(dict(state.ticket.__dict__, status='NEW', reported_priority=3))
    response = investigate_ticket(client, 'TST-0001', store=store)
    assert 'Scoped backend screening: 0 recent matching ticket(s)' in response['rationale']
    assert response['outage_detection']['threshold_met'] is False
    assert response['diagnosis_code'] is None
    assert response['next_question'] is None
    assert response['completed_actions'] == []

def test_evidence_requirement_markers_survive_without_unredacting_secrets():
    from wxo_langgraph.agent import sanitize
    marker = 'diagnosis_confirmed_by_current_ticket_evidence'
    payload = sanitize({'required_evidence': [marker], 'description': 'password=FakeSecret123'})
    assert payload['required_evidence'] == [marker]
    assert 'FakeSecret123' not in payload['description']
    assert sanitize({'description': 'api_key=' + marker})['description'] == 'api_key=[REDACTED]'

def test_later_operational_monitor_cannot_discard_supported_shared_issue():
    state = before_answer()
    submit_answer(state, 'no', 'ANSWER-NO')
    add_evidence(state, Evidence('MONITOR-NEW', 'Monitor reports operational', {'state': 'OPERATIONAL'},
        'diagnostic_check', contradicts=['VPN_OUTAGE']))
    assert any(c.diagnosis_id == 'VPN_OUTAGE' for c in state.candidates)
    assert state.final_diagnosis is None
    assert state.status == 'escalated'

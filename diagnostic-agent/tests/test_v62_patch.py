"""Persistent regressions for the consolidated v6.2 fixes."""
import json
from pathlib import Path

import pytest
from diagnostic_agent.answers import interpret_answer, diagnostic_findings
from diagnostic_agent.backend_client import BackendRequestError
from diagnostic_agent.conversation import render_reply
from diagnostic_agent.engine import reinterpret_saved_answers, reconcile_supported_hypotheses, reassess_review_state
from diagnostic_agent.integrated import submit_correction_for_review, investigate_ticket
from diagnostic_agent.session_store import _state_from_dict
from wxo_langgraph.agent import MessageSessionStore
from test_backend_integration import FakeBackend

ROOT = Path(__file__).resolve().parents[1]
PEER = 'Can colleagues at the same site connect to VPN right now?'
LOCAL = 'Does the VPN client show a local configuration or credential error?'


@pytest.mark.parametrize('text,field,expected,question', [
    ('No colleagues can connect to VPN.', 'peer_vpn_connection', 'FAILS', PEER),
    ('None of my colleagues can connect to VPN.', 'peer_vpn_connection', 'FAILS', PEER),
    ('The VPN client reports a local configuration error.', 'vpn_client_error', 'LOCAL_CONFIGURATION', LOCAL),
    ('The VPN client reports a credential error.', 'vpn_client_error', 'AUTHENTICATION', LOCAL),
])
def test_specific_reports_keep_their_meaning(text, field, expected, question):
    assert interpret_answer(question, text)['facts'][field] == expected


@pytest.mark.parametrize('text', [
    'Yes, colleagues can connect—actually, none can.',
    'None of my colleagues cannot connect.',
    'Yes, colleagues can connect, but no, colleagues cannot connect.',
])
def test_conflicting_and_double_negative_answers_need_clarification(text):
    assert interpret_answer(PEER, text) is None


def document():
    return json.loads((ROOT / 'docs/CHK-f6b3cd70a0c64c9b.json').read_text(encoding='utf-8'))


def test_old_generic_vpn_fact_upgraded_using_original_evidence_id():
    state = _state_from_dict(document()['session']['snapshot'])
    item = state.evidence[-1]
    item.value = 'The VPN client reports a local configuration error.'
    state.ticket.metadata['interpreted_answers'][item.evidence_id]['facts']['vpn_client_error'] = 'REPORTED'
    original = [e.evidence_id for e in state.evidence]
    reinterpret_saved_answers(state)
    reinterpret_saved_answers(state)
    assert state.ticket.metadata['interpreted_answers'][item.evidence_id]['facts']['vpn_client_error'] == 'LOCAL_CONFIGURATION'
    assert [e.evidence_id for e in state.evidence] == original
    assert 'local-configuration' in diagnostic_findings(state)['leading_hypothesis']['description']


@pytest.mark.parametrize('text,expected', [
    ('None of my colleagues can connect to VPN.', 'FAILS'),
    ('Yes, colleagues can connect—actually, none can.', None),
])
def test_saved_wrong_peer_interpretation_is_repaired(text, expected):
    state = _state_from_dict(document()['session']['snapshot'])
    item = state.evidence[-1]
    item.value = text
    item.description = 'User answered the diagnostic question: ' + PEER
    item.supports, item.contradicts = ['VPN_CLIENT_ISSUE'], ['VPN_OUTAGE']
    state.ticket.metadata['interpreted_answers'][item.evidence_id] = {
        'question': PEER, 'facts': {'peer_vpn_connection': 'WORKS'}}
    state.status, state.final_diagnosis = 'diagnosed', 'VPN_CLIENT_ISSUE'
    reinterpret_saved_answers(state)
    reconcile_supported_hypotheses(state)
    reassess_review_state(state)
    facts = state.ticket.metadata['interpreted_answers'].get(item.evidence_id, {}).get('facts', {})
    assert facts.get('peer_vpn_connection') == expected
    assert state.final_diagnosis is None
    if expected:
        assert state.status == 'escalated'
        assert any(c.diagnosis_id == 'VPN_OUTAGE' for c in state.candidates)


class CorrectionBackend(FakeBackend):
    def add_worklog_entry(self, tid, payload):
        self.calls.append(('add_worklog_entry', payload))
        return {'worklog_id': 'WL-CORRECTION', 'evidence_ids': ['EV-ACTUAL-CORRECTION']}
    def record_diagnostic_result(self, tid, payload):
        self.calls.append(('record_diagnostic_result', payload))
        return {'diagnostic_result_id': 'DR-CORRECTION', 'version': 7}


def test_backend_correction_audited_and_not_reconfirmed_on_resume():
    session = document()['session']
    session['snapshot']['status'] = 'diagnosed'
    session['snapshot']['final_diagnosis'] = 'VPN_CLIENT_ISSUE'
    client = CorrectionBackend({**session['snapshot']['ticket'], 'affected_person_id': 'USR-AFFECTED', 'status': 'NEW'})
    store = MessageSessionStore(session)
    text = 'Correction: colleagues cannot connect either.'
    result = submit_correction_for_review(client, session['ticket_id'], text, 'LOGICAL-REQUEST-1', store)
    assert result['diagnosis_code'] is None and result['recommended_action'] == 'ESCALATE'
    assert result['diagnostic_result_id'] == 'DR-CORRECTION'
    assert result['diagnostic_result_version'] == 7
    assert result['evidence_ids'][-1] == 'EV-ACTUAL-CORRECTION'
    payload = next(p for name, p in client.calls if name == 'add_worklog_entry')
    assert payload['evidence'][0]['source_type'] == 'USER_RESPONSE'
    assert payload['evidence'][0]['source_id'] == 'USR-AFFECTED'
    assert payload['entry_type'] == 'EVIDENCE'
    assert 'Supervisor' in render_reply(result, session)
    client.calls.clear()
    resumed = investigate_ticket(client, session['ticket_id'], store=store, diagnostic_review_mode=True)
    assert resumed['diagnosis_code'] is None and resumed['recommended_action'] == 'ESCALATE'
    assert not any(name.startswith('check_') for name, _ in client.calls)


@pytest.mark.parametrize('status', ['RESOLVED', 'CLOSED'])
def test_correction_does_not_mutate_terminal_backend_ticket(status):
    session = document()['session']
    client = CorrectionBackend({**session['snapshot']['ticket'], 'status': status})
    with pytest.raises(ValueError, match='cannot be mutated'):
        submit_correction_for_review(client, session['ticket_id'], 'Correction: peers fail.',
            'REQ-1', MessageSessionStore(session))
    assert [name for name, _ in client.calls] == ['get_ticket_details']


def test_failed_correction_persistence_is_not_claimed_as_recorded():
    session = document()['session']
    class MissingEvidence(CorrectionBackend):
        def add_worklog_entry(self, tid, payload):
            return {'worklog_id': 'WL-NO-EVIDENCE'}
    client = MissingEvidence({**session['snapshot']['ticket'], 'status': 'NEW', 'affected_person_id': 'USR-001'})
    with pytest.raises(BackendRequestError, match='persisted user evidence ID'):
        submit_correction_for_review(client, session['ticket_id'], 'Correction: peers fail.',
            'REQ-1', MessageSessionStore(session))
    assert not session['snapshot']['ticket']['metadata'].get('pending_correction_review')

"""Regressions for the exact saved WXO VPN conversations that exposed v6 defects."""
import json
from copy import deepcopy
from pathlib import Path

from diagnostic_agent.engine import submit_answer, reconcile_supported_hypotheses, add_evidence
from diagnostic_agent.session_store import _state_from_dict
from diagnostic_agent.conversation import render_reply
from diagnostic_agent.models import Evidence
from diagnostic_agent.integrated import investigate_ticket
from wxo_langgraph.agent import MessageSessionStore
from test_conflicting_vpn_evidence import OutageBackend

DOCS = Path(__file__).resolve().parents[1] / 'docs'


def checkpoint(reference):
    return json.loads((DOCS / (reference + '.json')).read_text(encoding='utf-8'))


def saved_before_answer():
    return _state_from_dict(checkpoint('CHK-f6b3cd70a0c64c9b')['session']['snapshot'])


def test_saved_local_error_and_successful_peers_support_individual_pattern():
    state = saved_before_answer()
    submit_answer(state, 'Yes, colleagues at the same site can connect.', 'PREPATCH-PEERS-WORK')
    assert state.final_diagnosis == 'VPN_CLIENT_ISSUE'
    assert state.recommended_action == 'route'
    assert state.ticket.metadata['diagnosis_basis'] == 'REPORTED_DIAGNOSTIC_PATTERN'


def test_unknown_peer_status_never_becomes_outage_or_confirmed_diagnosis():
    state = saved_before_answer()
    submit_answer(state, 'I do not know whether colleagues can connect.', 'PREPATCH-PEERS-UNKNOWN')
    assert state.final_diagnosis is None
    assert state.evidence[-1].supports == state.evidence[-1].contradicts == []
    assert state.ticket.metadata['interpreted_answers'].get('PREPATCH-PEERS-UNKNOWN') is None


def test_saved_local_error_plus_peer_failure_requires_shared_service_screening():
    state = saved_before_answer()
    submit_answer(state, 'No, colleagues at the same site cannot connect either.', 'PREPATCH-PEERS-FAIL')
    assert state.status == 'escalated'
    assert state.final_diagnosis is None
    assert state.evidence[-1].supports == ['VPN_OUTAGE']
    assert any(c.diagnosis_id == 'VPN_OUTAGE' for c in state.candidates)
    assert 'Supervisor' in state.rationale
    assert 'screening' in state.rationale
    local = next(c for c in state.candidates if c.diagnosis_id == 'VPN_CLIENT_ISSUE')
    assert local.supporting_evidence_ids and local.contradicting_evidence_ids


def test_exact_wxo_shared_scope_reply_names_supervisor_and_screening():
    document = checkpoint('CHK-9d22ad1c02e64c7a')
    reply = render_reply(deepcopy(document['result']), deepcopy(document['session']))
    assert 'Supervisor' in reply
    assert 'screen' in reply.lower()


def test_saved_handoff_recovers_screening_without_new_answers_or_duplicate_candidates():
    document = checkpoint('CHK-9d22ad1c02e64c7a')
    session = document['session']
    original_ids = {e['evidence_id'] for e in session['snapshot']['evidence']}
    client = OutageBackend({**session['snapshot']['ticket'], 'status': 'NEW', 'reported_priority': 3})
    store = MessageSessionStore(session)
    for _ in range(2):
        result = investigate_ticket(client, session['ticket_id'], store=store, diagnostic_review_mode=True)
        assert result['recommended_action'] == 'ESCALATE'
        assert result['diagnosis_code'] is None
        assert result['next_question'] is None
        assert result['outage_detection']
        assert 'Supervisor' in render_reply(result, session)
    snapshot = session['snapshot']
    assert [c['diagnosis_id'] for c in snapshot['candidates']].count('VPN_OUTAGE') == 1
    assert original_ids <= {e['evidence_id'] for e in snapshot['evidence']}
    assert any(name == 'count_recent_tickets' for name, _ in client.calls)
    assert not any(name in {'resolve_ticket', 'assign_ticket', 'create_global_ticket'} for name, _ in client.calls)


def test_shared_observations_override_previous_individual_conclusion():
    state = saved_before_answer()
    submit_answer(state, 'Yes, colleagues at the same site can connect.', 'PEERS-YES')
    assert state.final_diagnosis == 'VPN_CLIENT_ISSUE'
    add_evidence(state, Evidence('LATER-SHARED', 'New shared-service observation', 'Several peers now fail',
        'user_answer', supports=['VPN_OUTAGE']))
    assert state.final_diagnosis is None
    assert state.status == 'escalated'
    assert 'Supervisor' in state.rationale


def test_retrieval_alone_cannot_introduce_shared_hypothesis():
    state = saved_before_answer()
    state.evidence.append(Evidence('RETRIEVED-ONLY', 'Retrieved outage article', 'VPN outage',
        'knowledge', supports=['VPN_OUTAGE']))
    reconcile_supported_hypotheses(state)
    assert not any(c.diagnosis_id == 'VPN_OUTAGE' for c in state.candidates)

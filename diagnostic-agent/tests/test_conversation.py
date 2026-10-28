import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from wxo_langgraph import agent
from diagnostic_agent.backend_client import BackendRequestError
from diagnostic_agent.conversation import save_checkpoint, load_checkpoint, render_reply, latest_checkpoint


class CheckpointBackend:
    def __init__(self):
        self.logs = []

    def add_worklog_entry(self, tid, payload):
        self.logs.append(payload)
        return {'worklog_id': 'WL-' + str(len(self.logs))}

    def get_ticket_details(self, tid):
        return {'ticket_id': tid, 'worklogs': list(reversed(self.logs))}


def checkpoint_session():
    return {'mode': 'backend', 'ticket_id': 'TST-TEXT', 'snapshot': {
        'ticket': {'ticket_id': 'TST-TEXT', 'language': 'en'}, 'status': 'in_progress',
        'evidence': [], 'next_question': 'Can you access other corporate applications with the same account?'}}


def test_backend_resume_uses_latest_result_identity_not_worklog_order():
    class CurrentBackend(CheckpointBackend):
        def get_ticket_details(self, tid):
            return {**super().get_ticket_details(tid), 'status': 'NEW',
                'latest_diagnostic_result': {'diagnostic_result_id': 'DR-CURRENT'}}
    backend = CurrentBackend()
    save_checkpoint(backend, 'TST-TEXT', checkpoint_session(), {'diagnostic_result_id': 'DR-OLD'})
    current_ref = save_checkpoint(backend, 'TST-TEXT', checkpoint_session(), {'diagnostic_result_id': 'DR-CURRENT'})
    restored = latest_checkpoint(backend, 'TST-TEXT')
    assert restored['session']['checkpoint_ref'] == current_ref
    assert restored['result']['diagnostic_result_id'] == 'DR-CURRENT'


def test_checkpoint_roundtrip_chunk_order_and_exact_ids():
    backend = CheckpointBackend()
    session = checkpoint_session()
    # Poorly compressible values force multiple independently audited NOTE chunks.
    import random
    rng = random.Random(41)
    session['snapshot']['evidence'] = [rng.randbytes(12000).hex()]
    ref = save_checkpoint(backend, 'TST-TEXT', session, {'diagnostic_result_id': 'DR-EXACT'})
    assert len(backend.logs) > 1
    assert len({log['action_id'] for log in backend.logs}) == len(backend.logs)
    assert all(log['entry_type'] == 'NOTE' for log in backend.logs)
    restored = load_checkpoint(backend, 'TST-TEXT', ref)
    assert restored['session']['snapshot'] == session['snapshot']
    assert restored['result']['diagnostic_result_id'] == 'DR-EXACT'
    assert restored['session']['checkpoint_ref'] == ref


@pytest.mark.parametrize('corruption', ['checksum', 'missing_part', 'wrong_ticket'])
def test_corrupt_checkpoints_fail_safely(corruption):
    backend = CheckpointBackend()
    ref = save_checkpoint(backend, 'TST-TEXT', checkpoint_session(), {})
    if corruption == 'missing_part':
        backend.logs.clear()
    elif corruption == 'checksum':
        data = json.loads(backend.logs[0]['rationale'])
        data['sha256'] = '0' * 64
        backend.logs[0]['rationale'] = json.dumps(data)
    with pytest.raises(BackendRequestError, match='could not be restored'):
        load_checkpoint(backend, 'OTHER' if corruption == 'wrong_ticket' else 'TST-TEXT', ref)


def test_plain_reply_and_metadata_resume_keep_secrets_out():
    config = {'configurable': {'mode': 'local'}}
    first = agent.create_agent(config).compile().invoke({'messages': [HumanMessage(content=json.dumps({
        'ticket_id': 'TST-TEXT', 'ticket': {'ticket_id': 'TST-TEXT', 'summary': 'Cannot sign in',
            'description': 'Portal access denied; password=FakeSecret123'}}))]})
    reply = first['messages'][-1]
    assert not reply.content.startswith('{')
    assert 'diagnostic_session' not in reply.content
    assert 'FakeSecret123' not in reply.model_dump_json()
    second = agent.create_agent(config).compile().invoke({'messages': first['messages'] + [HumanMessage(content='no')]})
    payload = agent.diagnostic_payload(second['messages'][-1])
    assert payload['diagnostic_session']['snapshot']['evidence'][-1]['value'] == 'no'


def test_backend_text_only_resume_survives_loss_of_all_message_metadata(monkeypatch):
    backend = CheckpointBackend()
    # Continuations now verify the persisted result identity before using state.
    backend.latest_id = 'DR-1'
    read_record = backend.get_ticket_details
    backend.get_ticket_details = lambda tid: {**read_record(tid), 'status': 'NEW',
        'latest_diagnostic_result': {'diagnostic_result_id': backend.latest_id}}
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', lambda **kwargs: backend)
    monkeypatch.setenv('DIAGNOSTIC_BACKEND_API_KEY', 'synthetic-key')

    def investigate(client, tid, store, **kwargs):
        store.session.update(checkpoint_session())
        return {'ticket_id': tid, 'recommended_action': 'ASK_MORE',
            'next_question': checkpoint_session()['snapshot']['next_question'], 'diagnostic_result_id': 'DR-1'}

    def answer(client, tid, answer, eid, store, **kwargs):
        assert store.session['snapshot']['next_question'].startswith('Can you access')
        assert answer == 'no'
        backend.latest_id = 'DR-2'
        return {'ticket_id': tid, 'recommended_action': 'ROUTE', 'diagnosis_code': 'PASSWORD_EXPIRED',
            'diagnostic_result_id': 'DR-2', 'completed_actions': [], 'next_question': None}

    monkeypatch.setattr(agent, 'investigate_ticket', investigate)
    monkeypatch.setattr(agent, 'submit_answer_and_continue', answer)
    first = agent.create_agent({}).compile().invoke({'messages': [HumanMessage(content='Investigate TST-TEXT')]})
    # Rebuild from scratch and supply ONLY the exact strings visible in WXO chat.
    second = agent.create_agent({}).compile().invoke({'messages': [
        AIMessage(content=first['messages'][-1].content), HumanMessage(content='no')]})
    reply = second['messages'][-1]
    assert 'expired password' in reply.content
    assert 'recommend a review' in reply.content
    assert not agent.diagnostic_payload(reply).get('error')
    logs_before_ack = len(backend.logs)
    third = agent.create_agent({}).compile().invoke({'messages': [
        AIMessage(content=reply.content), HumanMessage(content='Thanks')]})
    assert 'No further diagnostic answer' in third['messages'][-1].content
    assert len(backend.logs) == logs_before_ack


def test_checkpoint_failure_does_not_claim_safe_continuation(monkeypatch):
    monkeypatch.setenv('DIAGNOSTIC_BACKEND_API_KEY', 'synthetic-key')
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', lambda **kwargs: CheckpointBackend())
    def investigate(client, tid, store, **kwargs):
        store.session.update(checkpoint_session())
        return {'ticket_id': tid, 'recommended_action': 'ASK_MORE', 'next_question': 'Question?'}
    def rejected(*args):
        raise BackendRequestError('Checkpoint rejected', status=409)
    monkeypatch.setattr(agent, 'investigate_ticket', investigate)
    monkeypatch.setattr(agent, 'save_checkpoint', rejected)
    output = agent.create_agent({}).compile().invoke({'messages': [HumanMessage(content='TST-TEXT')]})
    assert 'couldn’t save' in output['messages'][-1].content
    assert agent.diagnostic_payload(output['messages'][-1])['checkpoint_error']
    assert 'Ref:' not in output['messages'][-1].content


def test_missing_checkpoint_does_not_treat_answer_as_new_investigation(monkeypatch):
    monkeypatch.setenv('DIAGNOSTIC_BACKEND_API_KEY', 'synthetic-key')
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', lambda **kwargs: CheckpointBackend())
    def forbidden(*args, **kwargs):
        raise AssertionError('Must not investigate an answer without restored context')
    monkeypatch.setattr(agent, 'investigate_ticket', forbidden)
    output = agent.create_agent({}).compile().invoke({'messages': [AIMessage(
        content='Question?\n\nTicket: TST-TEXT · Ref: CHK-0123456789abcdef'), HumanMessage(content='no')]})
    assert agent.diagnostic_payload(output['messages'][-1])['checkpoint_error']


def test_legacy_structured_history_resumes_as_plain_text():
    payload = json.loads((Path(__file__).parent / 'fixtures' / 'wxo_v41_handoff.json').read_text(encoding='utf-8'))
    output = agent.create_agent({}).compile().invoke({'messages': [
        AIMessage(content=json.dumps(payload)), HumanMessage(content='Thanks')]})
    assert not output['messages'][-1].content.startswith('{')
    assert agent.diagnostic_payload(output['messages'][-1])['handoff_status'] == 'AWAITING_SUPERVISOR'


def test_structured_output_is_explicit_debug_option():
    output = agent.create_agent({'configurable': {'mode': 'local', 'response_format': 'structured'}}).compile().invoke({
        'messages': [HumanMessage(content='Hello')]})
    assert json.loads(output['messages'][-1].content)['recommended_action'] == 'ASK_MORE'


def test_arabic_followup_preserves_language():
    config = {'configurable': {'mode': 'local'}}
    first = agent.create_agent(config).compile().invoke({'messages': [HumanMessage(content=json.dumps({
        'ticket_id': 'TST-AR', 'ticket': {'ticket_id': 'TST-AR', 'summary': 'Password expired',
            'description': 'Password expired', 'language': 'ar'}}))]})
    second = agent.create_agent(config).compile().invoke({'messages': first['messages'] + [HumanMessage(content='لا')]})
    assert agent.diagnostic_payload(second['messages'][-1])['diagnostic_session']['reply_language'] == 'ar'
    assert not second['messages'][-1].content.startswith('{')


def test_rendering_distinguishes_proposals_and_completed_actions():
    assert 'recommend' in render_reply({'recommended_action': 'ROUTE', 'diagnosis_code': 'PASSWORD_EXPIRED'}, {})
    assert 'requested a human review' not in render_reply({'recommended_action': 'ESCALATE'}, {})
    assert 'requested a human review' in render_reply({'recommended_action': 'ESCALATE', 'human_review': {'review_id': 'R-1'}}, {})
    text = render_reply({'recommended_action': 'ESCALATE', 'evidence_conflicts': ['conflict']}, {})
    assert 'outage is not confirmed' in text.lower()


def test_closed_ticket_never_writes_checkpoint(monkeypatch):
    monkeypatch.setenv('DIAGNOSTIC_BACKEND_API_KEY', 'synthetic-key')
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', lambda **kwargs: CheckpointBackend())
    def investigate(client, tid, store, **kwargs):
        store.session.update(checkpoint_session())
        return {'ticket_id': tid, 'status': 'CLOSED', 'outcome': 'ALREADY_CLOSED', 'recommended_action': 'NONE'}
    def forbidden(*args):
        raise AssertionError('Closed tickets must not be mutated')
    monkeypatch.setattr(agent, 'investigate_ticket', investigate)
    monkeypatch.setattr(agent, 'save_checkpoint', forbidden)
    output = agent.create_agent({}).compile().invoke({'messages': [HumanMessage(content='TST-TEXT')]})
    assert 'already resolved or closed' in output['messages'][-1].content

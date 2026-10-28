"""Native graph recovery with real checkpoint serialization and an in-memory backend.

No network. Continuation handlers are spies: these tests verify dispatch and
state recovery, while existing suites cover diagnostic and resolution behavior.
"""
import copy
import json
import sys
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage, AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wxo_langgraph import agent

TID = 'INC-RESUME-682'
DR = 'DR-RESUME-682'


@pytest.fixture
def backend(monkeypatch):
    first = agent.create_agent({'configurable': {'mode': 'local'}}).compile().invoke({
        'messages': [HumanMessage(content=json.dumps({'operation': 'investigate', 'ticket_id': TID,
            'ticket': {'ticket_id': TID, 'summary': 'Password expired',
                       'description': 'Cannot sign in; password expired'}}))]})
    payload = agent.diagnostic_payload(first['messages'][-1])
    session = copy.deepcopy(payload['diagnostic_session'])
    session.update(mode='backend', ticket_id=TID)
    result = {'ticket_id': TID, 'diagnostic_result_id': DR, 'recommended_action': 'ASK_MORE',
              'next_question': session['snapshot']['next_question']}
    record = {'ticket_id': TID, 'status': 'NEW', 'latest_diagnostic_result': {
        'diagnostic_result_id': DR}, 'worklogs': []}
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_ticket_details(self, tid):
            assert tid == TID
            return copy.deepcopy(record)

        def add_worklog_entry(self, tid, entry):
            assert tid == TID
            record['worklogs'].append({**copy.deepcopy(entry), 'timestamp': '2026-10-01T12:00:00Z'})

    client = Client()
    reference = agent.save_checkpoint(client, TID, session, result)
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', Client)

    def answer(client, tid, text, evidence_id, store, **kwargs):
        current = store.load(tid)
        assert current is not None
        calls.append(('answer', text, copy.deepcopy(store.session)))
        return result.copy()

    def resolution(client, tid, text, evidence_id, store, **kwargs):
        assert store.load(tid) is not None
        calls.append(('resolution_answer', text, copy.deepcopy(store.session)))
        return result.copy()

    monkeypatch.setattr(agent, 'submit_answer_and_continue', answer)
    monkeypatch.setattr(agent, 'continue_guided_resolution', resolution)
    return {'client': client, 'record': record, 'session': session, 'result': result,
            'reference': reference, 'calls': calls}


def invoke(backend, *, ref=True, history=None, response_format=None, **request):
    obj = {'operation': 'answer', 'ticket_id': TID, 'answer': 'yes', **request}
    if ref:
        obj['checkpoint_ref'] = backend['reference'] if ref is True else ref
    config = {'configurable': {'credentials': {'isys_it_backend_api_key': 'local-fake-key'}}}
    if response_format:
        config['configurable']['response_format'] = response_format
    output = agent.create_agent(config).compile().invoke({'messages': (history or []) + [
        HumanMessage(content=json.dumps(obj))]})
    return agent.diagnostic_payload(output['messages'][-1]), output['messages'][-1].content


@pytest.mark.parametrize('explicit', [True, False])
def test_fresh_graph_recovers_real_checkpoint_and_dispatches_once(backend, explicit):
    payload, _ = invoke(backend, ref=explicit)
    assert not payload.get('error')
    assert len(backend['calls']) == 1
    assert backend['calls'][0][:2] == ('answer', 'yes')


@pytest.mark.parametrize('stage', ['WAIT_STEP', 'WAIT_SUCCESS'])
def test_recovered_guidance_stage_uses_existing_resolution_handler(backend, stage):
    backend['session']['snapshot']['ticket']['metadata']['resolution_progress'] = {'stage': stage}
    backend['reference'] = agent.save_checkpoint(backend['client'], TID, backend['session'], backend['result'])
    payload, _ = invoke(backend, answer='Done' if stage == 'WAIT_STEP' else 'Yes')
    assert not payload.get('error')
    assert len(backend['calls']) == 1
    assert backend['calls'][0][0] == 'resolution_answer'


def test_corrupt_explicit_checkpoint_never_calls_answer(backend):
    part = json.loads(backend['record']['worklogs'][0]['rationale'])
    part['sha256'] = '0' * 64
    backend['record']['worklogs'][0]['rationale'] = json.dumps(part)
    payload, visible = invoke(backend)
    assert payload['integration_error'] == 'DIAGNOSTIC_RESUME_BLOCKED'
    assert 'continuation is blocked' in visible
    assert 'resend the ticket ID' not in visible
    assert backend['calls'] == []


def test_newer_result_rejects_old_checkpoint(backend):
    backend['record']['latest_diagnostic_result']['diagnostic_result_id'] = 'DR-NEW'
    payload, _ = invoke(backend)
    assert payload['integration_error'] == 'DIAGNOSTIC_RESUME_BLOCKED'
    assert backend['calls'] == []


def test_consumed_answer_cannot_replay_old_checkpoint(backend):
    backend['record']['worklogs'].append({'summary':
        '[DiagnosticAgent] User answered the guided resolution question.', 'evidence_ids': ['EV-NEW']})
    payload, _ = invoke(backend)
    assert payload['integration_error'] == 'DIAGNOSTIC_RESUME_BLOCKED'
    assert backend['calls'] == []


def test_fallback_selects_current_evidence_even_with_frozen_clock(backend):
    backend['record']['worklogs'].append({'summary':
        '[DiagnosticAgent] User answered the guided resolution question.', 'evidence_ids': ['EV-NEW']})
    backend['session']['snapshot']['evidence'].append({'evidence_id': 'EV-NEW',
        'description': 'Step done', 'value': 'Done', 'source': 'user_answer'})
    agent.save_checkpoint(backend['client'], TID, backend['session'], backend['result'])
    # Call recovery directly: this probe verifies selection, not a diagnosis from a minimal evidence fixture.
    document = agent.restore_continuation(backend['client'], TID)
    assert any(e['evidence_id'] == 'EV-NEW' for e in document['session']['snapshot']['evidence'])


def test_ambiguous_same_result_states_require_explicit_reference(backend):
    backend['session']['snapshot']['next_question'] = 'A different question'
    agent.save_checkpoint(backend['client'], TID, backend['session'], backend['result'])
    payload, _ = invoke(backend, ref=False)
    assert 'Multiple different pending checkpoints' in payload['error']
    assert backend['calls'] == []


@pytest.mark.parametrize('status', ['RESOLVED', 'CLOSED'])
def test_terminal_ticket_does_not_process_answer_or_write_checkpoint(backend, status):
    backend['record']['status'] = status
    before = len(backend['record']['worklogs'])
    payload, _ = invoke(backend)
    assert payload['outcome'] == 'ALREADY_CLOSED'
    assert backend['calls'] == []
    assert len(backend['record']['worklogs']) == before


def test_missing_checkpoint_reports_specific_error_without_writes(backend):
    backend['record']['worklogs'].clear()
    payload, _ = invoke(backend, ref=False)
    assert payload['integration_error'] == 'DIAGNOSTIC_RESUME_BLOCKED'
    assert backend['calls'] == []
    assert backend['record']['worklogs'] == []


def test_existing_native_session_is_checked_against_backend(backend):
    history = [AIMessage(content='Actual prior question', additional_kwargs={'isys_diagnostic': {
        **backend['result'], 'diagnostic_session': copy.deepcopy(backend['session'])}})]
    payload, _ = invoke(backend, ref=False, history=history)
    assert not payload.get('error')
    assert len(backend['calls']) == 1


def test_stale_retained_session_is_not_silently_advanced(backend):
    history = [AIMessage(content='Old question', additional_kwargs={'isys_diagnostic': {
        **backend['result'], 'diagnostic_session': copy.deepcopy(backend['session'])}})]
    backend['record']['latest_diagnostic_result']['diagnostic_result_id'] = 'DR-NEW'
    payload, _ = invoke(backend, ref=False, history=history)
    assert payload['integration_error'] == 'DIAGNOSTIC_RESUME_BLOCKED'
    assert backend['calls'] == []


def test_invalid_checkpoint_reference_is_not_accepted(backend):
    payload, _ = invoke(backend, ref='not-a-checkpoint')
    assert payload['integration_error'] == 'DIAGNOSTIC_RESUME_BLOCKED'
    assert backend['calls'] == []


def test_resume_errors_preserve_explicit_structured_output(backend):
    payload, visible = invoke(backend, ref='invalid', response_format='structured')
    assert json.loads(visible)['integration_error'] == 'DIAGNOSTIC_RESUME_BLOCKED'
    assert payload['completed_actions'] == []


@pytest.mark.parametrize('explicit_ref', [True, False])
def test_real_handlers_finish_resolution_across_fresh_invocations(monkeypatch, explicit_ref):
    from test_guided_resolution_delivery import ResolutionBackend

    class AuditedBackend(ResolutionBackend):
        def add_worklog_entry(self, tid, payload):
            response = super().add_worklog_entry(tid, payload)
            self.logs[-1]['evidence_ids'] = response.get('evidence_ids', [])
            return response

    client = AuditedBackend()
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', lambda **kwargs: client)
    config = {'configurable': {'credentials': {'isys_it_backend_api_key': 'local-fake-key'}}}
    tid = client.ticket['ticket_id']

    def fresh(request):
        output = agent.create_agent(config).compile().invoke({'messages': [
            HumanMessage(content=json.dumps(request))]})
        return agent.diagnostic_payload(output['messages'][-1])

    result = fresh({'operation': 'investigate', 'ticket_id': tid})
    first_ref = result['diagnostic_session']['checkpoint_ref']

    def reply(answer):
        nonlocal result
        request = {'operation': 'answer', 'ticket_id': tid, 'answer': answer}
        if explicit_ref:
            request['checkpoint_ref'] = result['diagnostic_session']['checkpoint_ref']
        result = fresh(request)
        assert not result.get('error'), result

    for _ in range(3):
        question = result.get('next_question', '')
        reply('yes' if 'password' in question.lower() and 'expired' in question.lower()
              else 'I cannot access other corporate applications with this account either.')
        if result.get('outcome') == 'RESOLVE_READY':
            break
    assert result['outcome'] == 'RESOLVE_READY'
    # A consumed answer bound to the old question is blocked, not applied to the step.
    replay = fresh({'operation': 'answer', 'ticket_id': tid, 'answer': 'yes', 'checkpoint_ref': first_ref})
    assert replay['integration_error'] == 'DIAGNOSTIC_RESUME_BLOCKED'
    reply('Done')
    assert result['resolution_progress']['stage'] == 'WAIT_SUCCESS'
    assert not any(name == 'resolve_ticket' for name, _ in client.calls)
    reply('Yes')
    assert result['outcome'] == 'RESOLVED'
    assert client.ticket['status'] == 'RESOLVED'
    assert sum(name == 'resolve_ticket' for name, _ in client.calls) == 1

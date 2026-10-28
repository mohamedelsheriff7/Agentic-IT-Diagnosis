"""Regressions for observed duplicate questions, unknown accounts and stage drift."""
import copy
import json

import pytest
from langchain_core.messages import HumanMessage
from diagnostic_agent.answers import canonical_question, question_family, interpret_answer
from diagnostic_agent.backend_client import BackendRequestError
from diagnostic_agent.engine import choose_next_question
from diagnostic_agent.models import DiagnosticState, TicketInput, DiagnosisCandidate
from test_guided_resolution_delivery import ResolutionBackend
from wxo_langgraph import agent


@pytest.mark.parametrize('question', [
    'Does the error explicitly say your password expired?',
    'Does the sign-in error explicitly say the password has expired?',
    'Does the error message on the sign-in screen explicitly say that your password has expired?',
])
def test_expiry_question_aliases_retain_one_family(question):
    assert question_family(question) == 'account_message'
    assert interpret_answer(question, 'yes')['facts']['account_message'] == 'EXPIRED'


@pytest.mark.parametrize('answer,expected', [('yes', 'FAILS'), ('no', 'WORKS')])
def test_legacy_negative_other_application_question_keeps_its_polarity(answer, expected):
    q = 'Do other applications using the same identity also reject sign-in?'
    assert question_family(q) == 'other_apps'
    assert interpret_answer(q, answer)['facts']['other_application_access'] == expected


def test_rephrased_positive_and_negative_answers_agree():
    positive = interpret_answer('Can you access other corporate applications with the same account?', 'no')
    negative = interpret_answer('Do other applications using the same identity also reject sign-in?', 'yes')
    assert positive['facts'] == negative['facts']


def test_unknown_article_arabic_questions_do_not_repeat_english_scope():
    state = DiagnosticState(ticket=TicketInput('TEST-Q', 'Portal fails', 'Portal fails after sign-in',
        language='en', metadata={'diagnostic_review_mode': True}),
        candidates=[DiagnosisCandidate('UNKNOWN_ISSUE', 'Unknown', 'Service Desk', 'Unclassified', 'GRP-L1')])
    state.knowledge_matches = [{'diagnosis_code': 'UNKNOWN_ISSUE', 'questions': [
        'ما هو التطبيق الذي لا يعمل؟', 'ما هي رسالة الخطأ ومتى بدأت المشكلة؟']}]
    state.questions_asked = ['What exact error message do you see, and when did the problem start?']
    q = choose_next_question(state)
    assert q == 'Which specific application or service is affected?'
    state.questions_asked.append(q)
    assert choose_next_question(state) is None


@pytest.mark.parametrize('question', ['ما هو التطبيق الذي لا يعمل؟',
    'Which application or device were you using when you noticed the problem?'])
def test_scope_aliases_share_one_family(question):
    assert question_family(question) == 'application_scope'
    assert canonical_question(question) == 'Which specific application or service is affected?'


class AuditedBackend(ResolutionBackend):
    def add_worklog_entry(self, tid, payload):
        result = super().add_worklog_entry(tid, payload)
        self.logs[-1]['evidence_ids'] = result.get('evidence_ids', [])
        return result


class UnknownAccountBackend(AuditedBackend):
    def __init__(self, error_status=None):
        super().__init__()
        self.account_calls = 0
        self.error_status = error_status

    def check_account_status(self, payload):
        self.account_calls += 1
        if self.error_status:
            raise BackendRequestError('Synthetic account check failed.', status=self.error_status)
        return {'evidence_id': 'EV-UNKNOWN-ACCOUNT', 'enabled': 'UNKNOWN', 'locked': 'UNKNOWN',
                'password_expired': 'UNKNOWN', 'mfa_enrolled': 'UNKNOWN', 'mfa_locked': 'UNKNOWN'}


def fresh(monkeypatch, backend, request):
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', lambda **kwargs: backend)
    config = {'configurable': {'credentials': {'isys_it_backend_api_key': 'local-test-only'}}}
    output = agent.create_agent(config).compile().invoke({'messages': [HumanMessage(content=json.dumps(request))]})
    return agent.diagnostic_payload(output['messages'][-1]), output['messages'][-1].content


@pytest.mark.parametrize('error_status,category', [(None, 'UNKNOWN'), (404, 'UNAVAILABLE'),
    (422, 'REJECTED'), (503, 'UNAVAILABLE')])
def test_unknown_or_failed_account_check_has_bounded_human_fallback(monkeypatch, error_status, category):
    backend = UnknownAccountBackend(error_status)
    tid = backend.ticket['ticket_id']
    result, _ = fresh(monkeypatch, backend, {'operation': 'investigate', 'ticket_id': tid})
    seen = []
    for _ in range(3):
        if result['recommended_action'] != 'ASK_MORE':
            break
        family = question_family(result['next_question'])
        assert family not in seen
        seen.append(family)
        answer = 'yes' if family == 'account_message' else 'no'
        result, visible = fresh(monkeypatch, backend, {'operation': 'answer', 'ticket_id': tid,
            'answer': answer, 'checkpoint_ref': result['diagnostic_session']['checkpoint_ref']})
    assert seen == ['account_message', 'other_apps']
    assert backend.account_calls == 1
    assert result['recommended_action'] == 'ESCALATE'
    assert result['outcome'] == 'HUMAN_REQUIRED'
    assert result['diagnosis_code'] is None
    assert result['diagnostic_blocker']['kind'] == 'ACCOUNT_VERIFICATION_UNAVAILABLE'
    assert result['account_check_status']['status'] == category
    assert 'no diagnosis or shared outage is confirmed' in visible
    assert backend.ticket['status'] == 'NEW'
    assert not any(name in {'resolve_ticket', 'assign_ticket', 'create_global_ticket'} for name, _ in backend.calls)


def test_completion_word_cannot_answer_unfinished_diagnostic_question(monkeypatch):
    backend = AuditedBackend()
    tid = backend.ticket['ticket_id']
    result, _ = fresh(monkeypatch, backend, {'operation': 'investigate', 'ticket_id': tid})
    reference = result['diagnostic_session']['checkpoint_ref']
    logs_before = copy.deepcopy(backend.logs)
    blocked, visible = fresh(monkeypatch, backend, {'operation': 'answer', 'ticket_id': tid,
        'answer': 'Done .', 'checkpoint_ref': reference})
    assert blocked['integration_error'] == 'DIAGNOSTIC_ANSWER_STAGE_MISMATCH'
    assert backend.logs == logs_before
    assert result['next_question'] in visible
    assert reference in visible
    assert blocked['completed_actions'] == []


def test_status_only_unknown_result_is_not_rechecked_on_each_reply(monkeypatch):
    class StatusOnlyBackend(UnknownAccountBackend):
        def check_account_status(self, payload):
            self.account_calls += 1
            return {'status': 'UNKNOWN', 'evidence_id': 'EV-STATUS-UNKNOWN'}
    backend = StatusOnlyBackend()
    tid = backend.ticket['ticket_id']
    result, _ = fresh(monkeypatch, backend, {'operation': 'investigate', 'ticket_id': tid})
    for answer in ['yes', 'no']:
        result, _ = fresh(monkeypatch, backend, {'operation': 'answer', 'ticket_id': tid,
            'answer': answer, 'checkpoint_ref': result['diagnostic_session']['checkpoint_ref']})
    assert backend.account_calls == 1
    assert result['recommended_action'] == 'ESCALATE'


def test_v682_saved_unknown_evidence_recovers_attempt_metadata(monkeypatch):
    from diagnostic_agent.integrated import _run_diagnostic_checks
    backend = UnknownAccountBackend()
    tid = backend.ticket['ticket_id']
    result, _ = fresh(monkeypatch, backend, {'operation': 'investigate', 'ticket_id': tid})
    state = agent._state_from_dict(result['diagnostic_session']['snapshot'])
    state.ticket.metadata.pop('account_check_attempt')
    _run_diagnostic_checks(backend, backend.get_ticket_details(tid), state)
    assert state.ticket.metadata['account_check_attempt']['status'] == 'UNKNOWN'
    assert backend.account_calls == 1


def test_english_portal_conversation_retains_english_without_equivalent_repeats():
    config = {'configurable': {'mode': 'local'}}
    messages = [HumanMessage(content=json.dumps({'operation': 'investigate', 'ticket_id': 'TEST-PORTAL',
        'ticket': {'ticket_id': 'TEST-PORTAL', 'summary': 'Portal fails after sign-in',
            'description': 'Portal fails after sign-in, but mail works.', 'language': 'en'}}))]
    families = []
    for answer in ['The exact error is unavailable; mail works.',
                   'I am using the web portal. I do not know its specific name.']:
        output = agent.create_agent(config).compile().invoke({'messages': messages})
        result = agent.diagnostic_payload(output['messages'][-1])
        question = result.get('next_question')
        if not question:
            break
        family = question_family(question)
        assert family not in families
        families.append(family)
        assert not any('\u0600' <= c <= '\u06ff' for c in output['messages'][-1].content)
        messages = output['messages'] + [HumanMessage(content=answer)]
    assert families == ['error_detail', 'application_scope']


def test_arabic_scope_rendering_preserves_explicit_language():
    text = agent.render_reply({'ticket_id': 'TEST-AR', 'recommended_action': 'ASK_MORE',
        'next_question': 'Which specific application or service is affected?'}, {}, 'ar')
    assert 'ما اسم التطبيق' in text

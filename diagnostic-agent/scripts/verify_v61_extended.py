"""Extended decision/safety checks: shipped ZIP, offline simulated tools only."""
import importlib.util
import argparse
import json
import sys
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--package', default='dist/isys-diagnostic-langgraph-v6.1.zip')
parser.add_argument('--report', default='docs/v61_extended_results.json')
args = parser.parse_args()
temporary = tempfile.TemporaryDirectory(prefix='v61-extended-', dir=ROOT / 'dist')
entrypoint = Path(temporary.name) / 'agent.py'
with zipfile.ZipFile(ROOT / args.package) as archive:
    entrypoint.write_bytes(archive.read('agent.py'))
spec = importlib.util.spec_from_file_location('extended_agent', entrypoint)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)
from diagnostic_agent.answers import interpret_answer
from diagnostic_agent.backend_client import BackendRequestError
from langchain_core.messages import HumanMessage, AIMessage

results = []
report = ROOT / args.report


def record(name, passed, **detail):
    results.append({'test': name, 'passed': bool(passed), **detail})
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'test': name, 'passed': bool(passed)}), flush=True)


def invoke(messages, mode='local'):
    return agent.create_agent({'configurable': {'mode': mode,
        'credentials': {'isys_it_backend_api_key': 'synthetic-offline-key'}}}).compile().invoke({'messages': messages})


def from_checkpoint(answer):
    prior = json.loads((ROOT / 'docs/CHK-f6b3cd70a0c64c9b.json').read_text(encoding='utf-8'))
    prior['diagnostic_session'] = prior.pop('session')
    payload = {**prior.pop('result'), 'diagnostic_session': prior['diagnostic_session']}
    payload['diagnostic_session']['mode'] = 'local'
    chat = invoke([AIMessage(content='Previous VPN question', additional_kwargs={'isys_diagnostic': payload}),
        HumanMessage(content=answer)])
    return agent.diagnostic_payload(chat['messages'][-1]), chat['messages'][-1].content


peer = 'Can colleagues at the same site connect to VPN right now?'
for name, text in (
    ('self_correcting_answer', 'Yes, colleagues can connect—actually, none can.'),
    ('explicit_conflicting_answer', 'Yes, colleagues can connect, but no, colleagues cannot connect.'),
):
    actual = interpret_answer(peer, text)
    record(name, actual is None, answer=text, actual=actual,
        expected='Clarify the conflicting statement; do not select the first positive clause.')

text = 'It was only me earlier; now five colleagues at the same site cannot connect to VPN.'
payload, reply = from_checkpoint(text)
record('scope_expands_during_investigation', payload['recommended_action'] == 'ESCALATE'
    and 'VPN_OUTAGE' in {c.get('diagnosis_id') if isinstance(c, dict) else c
        for c in payload['remaining_candidates']} and 'Supervisor' in reply,
    reply=reply, evidence=payload['diagnostic_session']['snapshot']['evidence'][-1])

question = 'Can you access other corporate applications with the same account?'
text = 'Email works, but it was already signed in. New logins fail.'
actual = interpret_answer(question, text)
record('cached_session_does_not_exclude_account', actual is None or
    actual.get('facts', {}).get('other_application_access') != 'WORKS', actual=actual)
record('cached_session_left_unclassified', actual is None,
    expected='Leave the ambiguous cached-session report unclassified rather than assuming fresh access works.', actual=actual)


class Backend:
    def __init__(self, tool_mode='unknown', terminal=None):
        self.tool_mode = tool_mode
        self.terminal = terminal
        self.calls = []
        self.logs = {}
        self.latest = {}
    def get_ticket_details(self, tid):
        self.calls.append(('get_ticket_details', tid))
        return {'ticket_id': tid, 'summary': 'Password expired; cannot sign in' if 'AUTH' in tid else 'VPN client cannot connect',
            'description': 'Sign-in fails' if 'AUTH' in tid else 'VPN connection fails',
            'status': self.terminal or 'NEW', 'reported_priority': 3, 'reported_by_id': 'USR-001',
            'affected_person_id': 'USR-001', 'configuration_item_id': 'CI-001', 'location_id': 'LOC-001',
            'worklogs': self.logs.get(tid, []), 'latest_diagnostic_result': self.latest.get(tid)}
    def search_diagnostic_knowledge(self, payload):
        return {'results': []}
    def search_similar_tickets(self, payload):
        return {'results': []}
    def check_account_status(self, payload):
        self.calls.append(('check_account_status', payload))
        if self.tool_mode == 'timeout':
            raise BackendRequestError('Simulated account check timed out.')
        return {'evidence_id': 'TOOL-UNKNOWN-ACCOUNT', 'enabled': 'UNKNOWN', 'locked': 'UNKNOWN',
            'password_expired': 'UNKNOWN', 'mfa_required': 'UNKNOWN', 'mfa_registered': 'UNKNOWN'}
    def check_application_entitlement(self, payload):
        return {'evidence_id': 'TOOL-UNKNOWN-ENT', 'entitled': 'UNKNOWN'}
    def check_service_health(self, payload):
        self.calls.append(('check_service_health', payload))
        if self.tool_mode == 'timeout':
            raise BackendRequestError('Simulated service check timed out.')
        return {'evidence_id': 'TOOL-UNKNOWN-SERVICE', 'state': 'UNKNOWN'}
    def record_diagnostic_result(self, tid, payload):
        self.calls.append(('record_diagnostic_result', payload))
        self.latest[tid] = {'diagnostic_result_id': 'DR-SIMULATED-' + str(len(self.calls)), 'version': 1}
        return self.latest[tid]
    def add_worklog_entry(self, tid, payload):
        self.calls.append(('add_worklog_entry', payload))
        self.logs.setdefault(tid, []).append(payload)
        return {'worklog_id': 'WL-SIMULATED', 'evidence_ids': ['EV-SIMULATED-ANSWER'] if payload.get('evidence') else []}
    def find_open_global_tickets(self, payload):
        return {'results': []}
    def count_recent_tickets(self, payload):
        return {'count': 0, 'matching_ticket_ids': []}
    def resolve_ticket(self, *args):
        self.calls.append(('resolve_ticket', args))
        raise AssertionError('Resolution must be blocked in these tests')


for tool_mode in ('unknown', 'timeout'):
    for family in ('AUTH', 'VPN'):
        backend = Backend(tool_mode)
        agent.DiagnosticBackendClient = lambda **kwargs: backend
        chat = invoke([HumanMessage(content='Investigate INC-' + family + '-' + tool_mode)], 'backend')
        payload = agent.diagnostic_payload(chat['messages'][-1])
        evidence = payload['diagnostic_session']['snapshot']['evidence']
        safe = payload.get('diagnosis_code') is None and all(
            not e['supports'] and not e['contradicts'] for e in evidence if e['source'] == 'diagnostic_check')
        record(f'{family}_{tool_mode}_not_healthy_or_diagnosed', safe,
            action=payload.get('recommended_action'), check_errors=payload.get('check_errors'))
        text = chat['messages'][-1].content.split('\n\nTicket:')[0].lower()
        record(f'{family}_{tool_mode}_visible_gap', any(term in text for term in
            ('unknown', 'unavailable', 'timed out', 'couldn’t check', 'could not check')),
            reply=chat['messages'][-1].content)

# Multiple open tickets in one native conversation, with ID-less answers.
def first(tid, summary, description):
    return HumanMessage(content=json.dumps({'ticket_id': tid, 'ticket': {
        'ticket_id': tid, 'summary': summary, 'description': description}}))
chat = invoke([first('INC-ISOLATION-A', 'DNS failure', 'Internal server names fail to resolve')])
a = deepcopy(agent.diagnostic_payload(chat['messages'][-1])['diagnostic_session'])
chat = invoke(chat['messages'] + [first('INC-ISOLATION-B', 'VPN client cannot connect', 'VPN connection fails')])
chat = invoke(chat['messages'] + [HumanMessage(content='Yes, colleagues at the same site can connect.')])
b = agent.diagnostic_payload(chat['messages'][-1])
record('idless_answer_applies_to_active_ticket', b['ticket_id'] == 'INC-ISOLATION-B'
    and not a['snapshot']['evidence'] and any('colleagues' in str(e['value'])
        for e in b['diagnostic_session']['snapshot']['evidence']))

# Recover A from its own message history: requesting a different ticket must
# neither reuse B's evidence nor silently drop A's persisted evidence.
chat = invoke([first('INC-ISOLATION-C', 'DNS failure', 'Internal server names fail to resolve')])
chat = invoke(chat['messages'] + [HumanMessage(content='Internal server names fail, but direct IP access works.')])
saved_c = agent.diagnostic_payload(chat['messages'][-1])['diagnostic_session']['snapshot']
chat = invoke(chat['messages'] + [first('INC-ISOLATION-D', 'VPN client cannot connect', 'VPN connection fails')])
chat = invoke(chat['messages'] + [HumanMessage(content='Investigate INC-ISOLATION-C')])
payload = agent.diagnostic_payload(chat['messages'][-1])
record('local_switch_back_recovers_saved_ticket', not payload.get('error')
    and payload['diagnostic_session']['snapshot']['ticket']['ticket_id'] == 'INC-ISOLATION-C',
    error=payload.get('error'), scope='Local mode; backend checkpoint recovery was tested separately.')

backend = Backend()
agent.DiagnosticBackendClient = lambda **kwargs: backend
chat = invoke([HumanMessage(content='Investigate INC-AUTH-SWITCH-A')], 'backend')
chat = invoke(chat['messages'] + [HumanMessage(content='I cannot access other corporate applications either.')], 'backend')
before = agent.diagnostic_payload(chat['messages'][-1])
ids = set(before['evidence_ids'])
chat = invoke(chat['messages'] + [HumanMessage(content='Investigate INC-VPN-SWITCH-B')], 'backend')
# Strip metadata on the latest assistant reply, as WXO can do.
history = [AIMessage(content=m.content) if m.type == 'ai' else m for m in chat['messages']]
chat = invoke(history + [HumanMessage(content='Investigate INC-AUTH-SWITCH-A')], 'backend')
payload = agent.diagnostic_payload(chat['messages'][-1])
record('backend_switch_back_recovers_saved_ticket', not payload.get('error')
    and payload['ticket_id'] == 'INC-AUTH-SWITCH-A' and ids <= set(payload['evidence_ids']),
    reply=chat['messages'][-1].content, error=payload.get('error'))

for status in ('RESOLVED', 'CLOSED'):
    backend = Backend(terminal=status)
    agent.DiagnosticBackendClient = lambda **kwargs: backend
    chat = invoke([HumanMessage(content='Investigate INC-AUTH-TERMINAL')], 'backend')
    record(status + '_investigation_read_only', all(name == 'get_ticket_details' for name, _ in backend.calls),
        calls=[name for name, _ in backend.calls])
    prior = json.loads((ROOT / 'docs/CHK-f6b3cd70a0c64c9b.json').read_text(encoding='utf-8'))
    incoming = {**prior['result'], 'diagnostic_session': prior['session']}
    backend.calls.clear()
    chat = invoke([AIMessage(content='Previous question', additional_kwargs={'isys_diagnostic': incoming}),
        HumanMessage(content='Correction: colleagues cannot connect either.')], 'backend')
    record(status + '_correction_read_only', all(name == 'get_ticket_details' for name, _ in backend.calls),
        error=agent.diagnostic_payload(chat['messages'][-1]).get('error'))

backend = Backend()
agent.DiagnosticBackendClient = lambda **kwargs: backend
reports = json.loads((ROOT / 'tests/fixtures/v5_batch_reports.json').read_text(encoding='utf-8'))
session = deepcopy(reports[0]['session'])
session['snapshot']['status'] = 'diagnosed'
session['snapshot']['final_diagnosis'] = 'PASSWORD_EXPIRED'
session['mode'] = 'backend'
tid = session['ticket_id']
prior = {'ticket_id': tid, 'recommended_action': 'ROUTE', 'diagnostic_session': session}
chat = invoke([AIMessage(content='IAM review recommended', additional_kwargs={'isys_diagnostic': prior}),
    HumanMessage(content='It works now.')], 'backend')
record('success_claim_does_not_resolve', not any(name == 'resolve_ticket' for name, _ in backend.calls)
    and agent.diagnostic_payload(chat['messages'][-1]).get('outcome') != 'RESOLVED')
chat = invoke([AIMessage(content='IAM review recommended', additional_kwargs={'isys_diagnostic': prior}),
    HumanMessage(content=json.dumps({'operation': 'confirm_resolution', 'ticket_id': tid,
        'confirmed_by_user': True, 'completed_step_ids': []}))], 'backend')
payload = agent.diagnostic_payload(chat['messages'][-1])
record('explicit_confirmation_cannot_bypass_draft_article', bool(payload.get('error'))
    and not any(name == 'resolve_ticket' for name, _ in backend.calls), error=payload.get('error'))

for label, text in (
    ('english', 'No, colleagues at the same site cannot connect either.'),
    ('arabic', 'لا، زملائي في نفس الموقع مش قادرين يتصلوا بالـ VPN.'),
    ('franco', 'la2, kol el zomala fel makan mesh 3arfeen yetwasalo bel VPN.'),
):
    payload, reply = from_checkpoint(text)
    facts = payload['diagnostic_session']['snapshot']['ticket']['metadata'].get('interpreted_answers', {})
    explicit_failure = any(entry.get('facts', {}).get('peer_vpn_connection') == 'FAILS' for entry in facts.values())
    clarify = payload['recommended_action'] == 'ASK_MORE' and bool(payload.get('next_question'))
    record('language_' + label + '_safe_decision_or_clarification', payload.get('diagnosis_code') is None
        and (explicit_failure or clarify), reply=reply, action=payload.get('recommended_action'),
        interpreted_peer_failure=explicit_failure)

print(json.dumps({'passed': sum(r['passed'] for r in results), 'total': len(results), 'report': str(report)}))

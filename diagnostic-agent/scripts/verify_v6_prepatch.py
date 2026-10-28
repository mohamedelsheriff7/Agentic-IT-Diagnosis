"""Characterize v6 before patching; synthetic clones, no assignments/resolution.

Runs the actual retained ZIP, including text-only history and fresh factories.
Writes expected/actual results without aborting on a diagnostic mismatch.
"""
import importlib.util
import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--package', default='dist/isys-diagnostic-langgraph-v6.zip')
parser.add_argument('--report', default='docs/v6_prepatch_results.json')
parser.add_argument('--saved-only', action='store_true')
args = parser.parse_args()
load_dotenv(ROOT / '.env')
temporary = tempfile.TemporaryDirectory(prefix='v6-prepatch-', dir=ROOT / 'dist')
entrypoint = Path(temporary.name) / 'agent.py'
with zipfile.ZipFile(ROOT / args.package) as bundle:
    entrypoint.write_bytes(bundle.read('agent.py'))
spec = importlib.util.spec_from_file_location('prepatch_v6', entrypoint)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)
from diagnostic_agent.backend_client import DiagnosticBackendClient
from diagnostic_agent.conversation import latest_checkpoint, load_checkpoint, render_reply
from diagnostic_agent.engine import submit_answer
from diagnostic_agent.session_store import _state_from_dict

client = DiagnosticBackendClient(timeout=12)
REPORT = ROOT / args.report
saved_only = args.saved_only
results = json.loads(REPORT.read_text(encoding='utf-8')) if saved_only and REPORT.exists() else []
results = [r for r in results if not r['test'].startswith('legacy_')]


def record(name, passed, **detail):
    results.append({'test': name, 'passed': bool(passed), **detail})
    REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'test': name, 'passed': bool(passed), **{k: v for k, v in detail.items()
        if k in {'ticket_id', 'actual_action', 'actual_diagnosis', 'error'}}}), flush=True)


def invoke(messages):
    output = agent.create_agent({}).compile().invoke({'messages': messages})
    message = output['messages'][-1]
    payload = agent.diagnostic_payload(message)
    if payload.get('error') or payload.get('checkpoint_error'):
        raise RuntimeError(payload.get('error') or payload['checkpoint_error'])
    return message, payload


def clone(source, suffix):
    import uuid
    raw = client.get_ticket_details(source)
    body = {k: raw[k] for k in ('summary', 'description', 'reported_by_id', 'affected_person_id',
        'reported_priority', 'domain', 'category', 'language', 'configuration_item_id', 'location_id')
        if raw.get(k) is not None}
    body.update(action_id='prepatch-' + uuid.uuid4().hex,
        summary=body['summary'] + ' [v6 prepatch ' + suffix + ']')
    return client.create_ticket(body)


# Explicitly test the missing branch: local error plus peer failure/unknown.
branches = (
    ('peers_work', 'Yes, colleagues at the same site can connect.'),
    ('peers_fail', 'No, colleagues at the same site cannot connect either.'),
    ('peers_unknown', 'I do not know whether colleagues can connect.'),
)
for branch, answer in (() if saved_only else branches):
    try:
        created = clone('INC-1fd0c8ed464e4970', branch)
        tid = created['ticket_id']
        message, payload = invoke([HumanMessage(content='Investigate ' + tid)])
        turns = [message.content]
        answered = set()
        for _ in range(4):
            question = payload.get('next_question')
            if not question or question in answered:
                break
            answered.add(question)
            response = answer if 'colleagues' in question else (
                'The VPN client reports a local configuration error.' if 'configuration or credential' in question
                else 'I do not know.')
            # Simulate WXO stripping metadata on every turn.
            message, payload = invoke([AIMessage(content=message.content), HumanMessage(content=response)])
            turns.extend([response, message.content])
        expected = ('ESCALATE' if branch == 'peers_fail' else 'ROUTE' if branch == 'peers_work' else None)
        passed = (payload['recommended_action'] == expected if expected else
            payload.get('diagnosis_code') is None and payload['recommended_action'] != 'RESOLVE')
        if branch == 'peers_fail':
            passed = passed and 'supervisor' in message.content.lower()
        record(branch, passed, ticket_id=tid, expected_action=expected,
            actual_action=payload['recommended_action'], actual_diagnosis=payload.get('diagnosis_code'),
            turns=turns, result=payload)
        final = client.get_ticket_details(tid)
        record(branch + '_no_assignment_or_resolution',
            final['status'] not in {'RESOLVED', 'CLOSED'}
            and final.get('owner_group_id') == created.get('owner_group_id')
            and payload.get('completed_actions') == [], ticket_id=tid)
    except Exception as exc:
        record(branch, False, error=str(exc))


# One conversation, explicit ticket switches, recreating the graph each turn.
history = []
switches = (
    ('switch_password', 'INC-0f1deda906e743a8', 'PASSWORD_EXPIRED'),
    ('switch_vpn', 'INC-1fd0c8ed464e4970', None),
    ('switch_dns', 'INC-d8a775438e974622', 'DNS_FAILURE'),
    ('switch_wifi', 'INC-1de93dbec7cc4105', 'WIFI_FAILURE'),
)
for name, tid, expected in (() if saved_only else switches):
    try:
        before = latest_checkpoint(client, tid)
        original_ids = {e['evidence_id'] for e in before['session']['snapshot']['evidence']} if before else set()
        history.append(HumanMessage(content='Investigate ' + tid))
        message, payload = invoke(history)
        history.append(AIMessage(content=message.content))
        snapshot = payload['diagnostic_session']['snapshot']
        ids = {e['evidence_id'] for e in snapshot['evidence']}
        passed = payload['ticket_id'] == tid and snapshot['ticket']['ticket_id'] == tid
        if expected:
            passed = passed and payload.get('diagnosis_code') == expected
        record(name, passed, ticket_id=tid, actual_action=payload['recommended_action'],
            actual_diagnosis=payload.get('diagnosis_code'), reply=message.content)
        repeated = payload.get('next_question') in {
                e['description'].removeprefix('User answered the diagnostic question: ')
                for e in snapshot['evidence'] if e['source'] == 'user_answer'}
        record(name + '_saved_answers_preserved', original_ids <= ids and not repeated,
            ticket_id=tid, repeated_answered_question=repeated)
    except Exception as exc:
        record(name, False, error=str(exc))

# The exact legacy case differs from fresh tickets: VPN_OUTAGE was never present.
try:
    tid = 'INC-1fd0c8ed464e4970'
    before = load_checkpoint(client, tid, 'CHK-f6b3cd70a0c64c9b')
    after = load_checkpoint(client, tid, 'CHK-9d22ad1c02e64c7a')
    state = _state_from_dict(before['session']['snapshot'])
    submit_answer(state, 'No, colleagues at the same site cannot connect either.', 'PREPATCH-PEERS-FAIL')
    codes = [c.diagnosis_id for c in state.candidates]
    record('legacy_snapshot_adds_shared_hypothesis', 'VPN_OUTAGE' in codes,
        ticket_id=tid, remaining_candidates=codes, evidence_supports=state.evidence[-1].supports,
        rationale=state.rationale)
    reply = render_reply(after['result'], after['session'])
    record('legacy_reply_requests_screening', 'supervisor' in reply.lower() and 'screen' in reply.lower(),
        ticket_id=tid, actual_action=after['result']['recommended_action'], reply=reply)
except Exception as exc:
    record('legacy_checkpoint_replay', False, error=str(exc))

print(json.dumps({'passed': sum(r['passed'] for r in results), 'total': len(results),
    'report': str(REPORT)}), flush=True)

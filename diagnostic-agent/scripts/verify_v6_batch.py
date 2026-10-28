"""Live validation of the consolidated v5 transcript fixes; synthetic records only."""
import json
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

root = Path(__file__).resolve().parents[1]
load_dotenv(root / '.env')
sys.path.insert(0, str(root))
from wxo_langgraph.agent import create_agent, diagnostic_payload
from diagnostic_agent.backend_client import DiagnosticBackendClient

client = DiagnosticBackendClient()
reports = json.loads((root / 'tests/fixtures/v5_batch_reports.json').read_text(encoding='utf-8'))
target = root / 'docs/v6_live_batch_results.json'
results = json.loads(target.read_text(encoding='utf-8')) if target.exists() else []


def invoke(messages):
    output = create_agent({}).compile().invoke({'messages': messages})
    message = output['messages'][-1]
    payload = diagnostic_payload(message)
    assert not payload.get('error'), payload.get('error')
    assert not payload.get('checkpoint_error'), payload.get('checkpoint_error')
    assert payload['completed_actions'] == []
    assert payload['recommended_action'] != 'RESOLVE'
    return message, payload


def record(entry):
    results.append(entry)
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in entry.items() if k != 'turns'}), flush=True)


for report in reports:
    test = report['test']
    tid = report['session']['ticket_id']
    if any(e['test'] == test and e['phase'] == 'fresh_text_only_chat' for e in results):
        continue
    message, payload = invoke([HumanMessage(content='Investigate ' + tid)])
    assert set(payload['evidence_ids']) == {e['evidence_id'] for e in report['session']['snapshot']['evidence']}
    if test in {'1', '2', '3', '5'}:
        assert payload['recommended_action'] == 'ROUTE'
        assert payload['diagnosis_code'] == {'1': 'PASSWORD_EXPIRED', '2': 'PASSWORD_EXPIRED', '3': 'DNS_FAILURE', '5': 'PRINTER_OFFLINE'}[test]
    else:
        assert payload['recommended_action'] == 'ASK_MORE'
    if not any(e['test'] == test and e['phase'] == 'saved_transcript' for e in results):
        record({'test': test, 'phase': 'saved_transcript', 'ticket_id': tid, 'result': 'PASS',
            'action': payload['recommended_action'], 'diagnosis': payload['diagnosis_code'], 'turns': [message.content]})

    original = client.get_ticket_details(tid)
    body = {k: original[k] for k in ('summary', 'description', 'reported_by_id', 'affected_person_id',
        'reported_priority', 'domain', 'category', 'language', 'configuration_item_id', 'location_id') if original.get(k) is not None}
    body.update(action_id='v6-verification-' + uuid.uuid4().hex, summary=body['summary'] + ' [v6 verification]')
    created = client.create_ticket(body)
    clone_id = created['ticket_id']
    message, payload = invoke([HumanMessage(content='Investigate ' + clone_id)])
    turns = [message.content]
    for step in range(4):
        question = payload.get('next_question')
        if not question or (test == '7' and step == 1):
            break
        if test in {'1', '2'}:
            if 'other corporate applications' in question:
                answer = 'no' if test == '1' else 'I cannot access other corporate applications with this account either.'
            else:
                answer = 'yes' if test == '1' else 'The sign-in screen explicitly says my password expired.'
        elif test == '3':
            assert step == 0, 'DNS repeated an answered question'
            answer = 'Internal server names fail, but direct IP access to the same server works. External websites open normally.'
        elif test == '4':
            answer = 'yes' if 'another device' in question else 'The affected device connects to a different approved network.'
        elif test == '5':
            answer = 'Everyone using that printer is affected.' if 'everyone' in question else 'Other users cannot reach the printer either.'
        elif test == '6':
            answer = 'Yes, colleagues at the same site can connect.' if 'colleagues' in question else 'local configuration'
        else:
            answer = 'I don’t know which service is affected or the exact error.'
        message, payload = invoke([AIMessage(content=message.content), HumanMessage(content=answer)])
        turns.extend([answer, message.content])
    if test == '7':
        assert payload['recommended_action'] == 'ASK_MORE' and 'application or device' in payload['next_question']
    else:
        assert payload['recommended_action'] == 'ROUTE', payload.get('rationale')
    final = client.get_ticket_details(clone_id)
    assert final['status'] not in {'RESOLVED', 'CLOSED'}
    assert final.get('owner_group_id') == created.get('owner_group_id')
    record({'test': test, 'phase': 'fresh_text_only_chat', 'ticket_id': clone_id, 'result': 'PASS',
        'action': payload['recommended_action'], 'diagnosis': payload['diagnosis_code'], 'turns': turns})

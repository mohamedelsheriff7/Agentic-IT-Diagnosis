"""Exercise visible-text-only WXO turns against one fresh synthetic ticket."""
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
reference = client.get_ticket_details('INC-0391caf699ab4dce')
created = client.create_ticket({'action_id': 'plain-text-test-' + uuid.uuid4().hex,
    'summary': 'Conversation verification: Password expired; cannot sign in',
    'description': 'I cannot sign in to corporate applications. The screen says my password expired.',
    'reported_by_id': reference['reported_by_id'], 'affected_person_id': reference['affected_person_id'],
    'reported_priority': 3})
tid = created['ticket_id']
report = {'ticket_id': tid, 'turns': []}

first = create_agent({}).compile().invoke({'messages': [HumanMessage(content='Investigate ' + tid)]})
message = first['messages'][-1]
payload = diagnostic_payload(message)
assert not payload.get('error'), payload.get('error')
assert not payload.get('checkpoint_error'), payload.get('checkpoint_error')
assert payload['recommended_action'] == 'ASK_MORE'
assert 'other corporate applications' in message.content
assert not message.content.startswith('{')
report['turns'].append({'reply': message.content, 'recommended_action': payload['recommended_action']})

# Native host worst case: no graph state, no additional_kwargs, only visible text.
second = create_agent({}).compile().invoke({'messages': [AIMessage(content=message.content), HumanMessage(content='no')]})
message = second['messages'][-1]
payload = diagnostic_payload(message)
assert not payload.get('error'), payload.get('error')
assert not payload.get('checkpoint_error'), payload.get('checkpoint_error')
assert payload['diagnosis_code'] == 'PASSWORD_EXPIRED'
assert payload['recommended_action'] == 'ROUTE'
assert payload['diagnostic_session']['snapshot']['evidence'][-1]['value'] == 'no'
assert 'recommend a review' in message.content
report['turns'].append({'reply': message.content, 'recommended_action': payload['recommended_action']})

before = client.get_ticket_details(tid)
third = create_agent({}).compile().invoke({'messages': [AIMessage(content=message.content), HumanMessage(content='Thanks')]})
message = third['messages'][-1]
assert diagnostic_payload(message)['handoff_status'] == 'AWAITING_SUPERVISOR'
after = client.get_ticket_details(tid)
assert len(after['worklogs']) == len(before['worklogs'])
assert after['status'] not in {'RESOLVED', 'CLOSED'}
assert after.get('owner_group_id') == created.get('owner_group_id')
report['turns'].append({'reply': message.content, 'handoff_status': 'AWAITING_SUPERVISOR'})
report.update(result='PASS', visible_text_only_resume='PASS', no_duplicate_acknowledgement_mutations='PASS',
    final_status=after['status'])
(root / 'docs' / 'conversational_backend_verification.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))

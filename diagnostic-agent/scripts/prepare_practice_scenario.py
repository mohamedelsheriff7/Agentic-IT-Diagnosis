"""Verify a password-expiry scenario on a twin, then create an untouched practice ticket."""
import json
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
root = Path(__file__).resolve().parents[1]
load_dotenv(root / '.env')
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'adk-project' / 'agents'))
from diagnostic_agent.backend_client import DiagnosticBackendClient
from wxo_langgraph.agent import create_agent, diagnostic_payload
client = DiagnosticBackendClient()

def create(label):
    return client.create_ticket({'action_id': 'practice-' + uuid.uuid4().hex,
        'summary': label + ': Password expired; cannot sign in',
        'description': 'I cannot sign in to corporate applications. The screen says my password expired.',
        'reported_by_id': 'USR-001', 'affected_person_id': 'USR-001', 'reported_priority': 3,
        'domain': 'Access Management', 'category': 'Authentication', 'language': 'en'})

validation = create('Scenario verification')
tid = validation['ticket_id']
first = create_agent({}).compile().invoke({'messages': [HumanMessage(content='Investigate ' + tid)]})
initial = diagnostic_payload(first['messages'][-1])
assert not initial.get('error'), initial.get('error')
assert initial['recommended_action'] == 'ASK_MORE'
question = initial['next_question']
answer = 'no' if 'other corporate applications' in question.lower() else 'yes'
second = create_agent({}).compile().invoke({'messages': first['messages'] + [HumanMessage(content=answer)]})
final = diagnostic_payload(second['messages'][-1])
assert not final.get('error'), final.get('error')
assert final['diagnosis_code'] == 'PASSWORD_EXPIRED', final
assert final['outcome'] == 'DIAGNOSED', final
assert final['recommended_action'] == 'ROUTE', final
assert final['completed_actions'] == []
practice = create('User practice scenario')
report = {'practice_ticket_id': practice['ticket_id'], 'validation_ticket_id': tid,
    'initial_question': initial['next_question'], 'answer': answer,
    'expected_outcome': final['outcome'], 'expected_diagnosis': final['diagnosis_code'],
    'expected_action': final['recommended_action'], 'expected_confidence': final['confidence'],
    'validation_evidence_ids': final['evidence_ids']}
(root / 'docs' / 'practice_password_scenario.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))

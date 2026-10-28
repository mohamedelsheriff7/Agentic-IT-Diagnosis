"""Create one synthetic integration ticket and exercise the native graph.

This intentionally records diagnostic worklogs; it never assigns or resolves.
"""
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
reference = client.get_ticket_details('TST-0001')
created = client.create_ticket({'action_id': 'langgraph-smoke-' + uuid.uuid4().hex,
    'summary': 'LangGraph integration test: Portal access denied',
    'description': 'Synthetic integration verification. Email works but Portal says access denied.',
    'reported_by_id': reference['reported_by_id'],
    'affected_person_id': reference['affected_person_id'], 'reported_priority': 3})
tid = created['ticket_id']
graph = create_agent({}).compile()
first = graph.invoke({'messages': [HumanMessage(content=tid)]})
result = diagnostic_payload(first['messages'][-1])
print(json.dumps({'ticket_id': tid, 'phase': 'investigate', 'action': result.get('recommended_action'),
    'outcome': result.get('outcome'), 'error': result.get('error'), 'backend_status': result.get('backend_status')}))
assert not result.get('error'), result.get('error')
assert result['diagnostic_result_id']
if result.get('next_question'):
    second = create_agent({}).compile().invoke({'messages': first['messages'] + [HumanMessage(content='Unknown, error code 512')]})
    reply = diagnostic_payload(second['messages'][-1])
    print(json.dumps({'ticket_id': tid, 'phase': 'answer', 'action': reply.get('recommended_action'),
        'error': reply.get('error'), 'backend_status': reply.get('backend_status')}))
    assert not reply.get('error'), reply.get('error')
final = client.get_ticket_details(tid)
assert final['status'] not in {'RESOLVED', 'CLOSED'}
print(json.dumps({'backend_native_graph': 'passed', 'ticket_id': tid, 'status': final['status']}))

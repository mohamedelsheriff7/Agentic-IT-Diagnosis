"""HTTP smoke of the locally hosted native graph factory, without backend writes."""
import json
import uuid
import urllib.request
from pathlib import Path
from dotenv import dotenv_values
key = dotenv_values(Path(__file__).resolve().parents[1] / '.env')['DIAGNOSTIC_SERVICE_API_KEY']
session_id = 'graph-smoke-' + uuid.uuid4().hex[:10]
tid = 'GRAPH-SMOKE-' + uuid.uuid4().hex[:8]

def send(message):
    body = json.dumps({'session_id': session_id, 'mode': 'local', 'message': message}).encode()
    request = urllib.request.Request('http://127.0.0.1:8080/langgraph/chat', data=body,
        headers={'Content-Type': 'application/json', 'X-API-Key': key})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)

first = send(json.dumps({'ticket_id': tid, 'ticket': {'ticket_id': tid,
    'summary': 'Cannot sign in', 'description': 'Portal access denied'}}))
assert first['framework'] == 'langgraph' and first['next_question']
second = send('Unknown error 512')
assert second['diagnostic_session']['snapshot']['evidence'][-1]['value'] == 'Unknown error 512'
assert second['completed_actions'] == []
print(json.dumps({'local_langgraph_http': 'passed', 'checkpointed_multi_turn': 'passed', 'session_id': session_id}))

"""Non-destructive local HTTP smoke: creates a synthetic local session only."""
import json
import sys
import uuid
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
key = dotenv_values(root / '.env')['DIAGNOSTIC_SERVICE_API_KEY']
base = 'http://127.0.0.1:8080'

def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, headers={
        'Content-Type': 'application/json', 'X-API-Key': key})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)

assert request('/health')['status'] == 'ok'
ticket_id = 'SMOKE-' + uuid.uuid4().hex[:10]
result = request('/investigations', {'mode': 'local', 'ticket_id': ticket_id,
    'ticket': {'ticket_id': ticket_id, 'summary': 'Cannot sign in', 'description': 'Portal access denied'}})
assert result['next_question']
answer = request(f'/investigations/{ticket_id}/answers', {'answer': 'Unknown, error 512', 'evidence_id': 'SMOKE-ANSWER-1'})
state = request(f'/investigations/{ticket_id}')['state']
assert state['evidence'][-1]['value'] == 'Unknown, error 512'
assert state['status'] != 'resolved'
assert request('/openapi.json')['openapi'] == '3.0.3'
print(json.dumps({'health': 'ok', 'multi_turn': 'passed', 'persisted_trace': 'passed',
    'openapi': '3.0.3', 'backend_actions': 'none', 'ticket_id': ticket_id}))

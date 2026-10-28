"""Resolve one explicitly synthetic password test using the native shipped ZIP."""
import importlib.util
import hashlib
import argparse
import json
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--package', default='dist/isys-diagnostic-langgraph-v6.6.zip')
parser.add_argument('--report', default='docs/v66_live_resolution_results.json')
args = parser.parse_args()
load_dotenv(ROOT / '.env')
temporary = tempfile.TemporaryDirectory(prefix='v66-resolution-', dir=ROOT / 'dist')
entry = Path(temporary.name) / 'agent.py'
with zipfile.ZipFile(ROOT / args.package) as package:
    entry.write_bytes(package.read('agent.py'))
spec = importlib.util.spec_from_file_location('live_resolution_agent', entry)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)
from diagnostic_agent.backend_client import DiagnosticBackendClient
client = DiagnosticBackendClient(timeout=15)
original = client.get_ticket_details('INC-0f1deda906e743a8')
body = {k: original[k] for k in ('reported_by_id', 'affected_person_id', 'domain', 'category',
    'configuration_item_id', 'location_id') if original.get(k) is not None}
body.update(action_id='resolution-test-' + uuid.uuid4().hex, reported_priority=3, language='en',
    summary='Password expired [synthetic guided resolution test]',
    description='I cannot sign in. The sign-in screen explicitly says my password expired.')
created = client.create_ticket(body)
tid = created['ticket_id']
report = {'ticket_id': tid, 'passed': False, 'turns': [], 'synthetic_user_simulation': True,
    'package_sha256': hashlib.sha256((ROOT / args.package).read_bytes()).hexdigest(),
    'note': 'No real account/password was changed; this tests the synthetic prototype workflow.'}
target = ROOT / args.report


def invoke(text, previous=None):
    messages = ([AIMessage(content=previous.content)] if previous else []) + [HumanMessage(content=text)]
    output = agent.create_agent({}).compile().invoke({'messages': messages})
    message = output['messages'][-1]
    payload = agent.diagnostic_payload(message)
    report['turns'].append({'user': text, 'reply': message.content,
        'result': output['diagnostic_result']})
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not payload.get('error'), payload.get('error')
    assert not payload.get('checkpoint_error'), payload.get('checkpoint_error')
    return message, payload


message, result = invoke('Investigate ' + tid)
for _ in range(4):
    if result['outcome'] == 'RESOLVE_READY':
        break
    question = result.get('next_question', '')
    answer = 'yes' if 'expired' in question.lower() else 'I cannot access other corporate applications with this account either.'
    message, result = invoke(answer, message)
assert result['outcome'] == 'RESOLVE_READY', result.get('rationale')
assert result['confidence'] == 'HIGH'
message, result = invoke('done', message)
assert result['resolution_progress']['stage'] == 'WAIT_SUCCESS'
assert client.get_ticket_details(tid)['status'] not in {'RESOLVED', 'CLOSED'}
message, result = invoke('yes', message)
assert result['outcome'] == 'RESOLVED'
final = client.get_ticket_details(tid)
assert final['status'] == 'RESOLVED' and final['linked_solution_id'] == 'KB-001'
assert 'TICKET_RESOLVED' in result['completed_actions']
report.update(passed=True, backend_status=final['status'], linked_solution_id=final['linked_solution_id'],
    diagnostic_result_id=result['diagnostic_result_id'])
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'turns'}))

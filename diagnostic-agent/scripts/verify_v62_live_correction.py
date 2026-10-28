"""Verify correction persistence and resume on one synthetic DNS clone."""
import importlib.util
import json
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
temporary = tempfile.TemporaryDirectory(prefix='v62-live-', dir=ROOT / 'dist')
entry = Path(temporary.name) / 'agent.py'
with zipfile.ZipFile(ROOT / 'dist/isys-diagnostic-langgraph-v6.2.zip') as package:
    entry.write_bytes(package.read('agent.py'))
spec = importlib.util.spec_from_file_location('live_correction_agent', entry)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)
from diagnostic_agent.backend_client import DiagnosticBackendClient
client = DiagnosticBackendClient(timeout=12)
original = client.get_ticket_details('INC-d8a775438e974622')
body = {k: original[k] for k in ('reported_by_id', 'affected_person_id', 'reported_priority',
    'domain', 'category', 'language', 'configuration_item_id', 'location_id') if original.get(k) is not None}
body.update(action_id='correction-verification-' + uuid.uuid4().hex, summary='DNS failure [v6.2 correction verification]',
    description='Internal server names fail to resolve.')
created = client.create_ticket(body)
tid = created['ticket_id']
(ROOT / 'docs/v62_live_correction_attempt.json').write_text(json.dumps({
    'ticket_id': tid, 'stage': 'CREATED', 'passed': False}, indent=2), encoding='utf-8')
turns = []


def invoke(messages):
    output = agent.create_agent({}).compile().invoke({'messages': messages})
    message = output['messages'][-1]
    payload = agent.diagnostic_payload(message)
    assert not payload.get('error'), payload.get('error')
    assert not payload.get('checkpoint_error'), payload.get('checkpoint_error')
    turns.append(message.content)
    return message, payload


message, result = invoke([HumanMessage(content='Investigate ' + tid)])
for answer in ('Internal server names fail, but direct IP access to the same server works.',
               'External websites open normally.'):
    turns.append(answer)
    message, result = invoke([AIMessage(content=message.content), HumanMessage(content=answer)])
assert result['diagnosis_code'] == 'DNS_FAILURE' and result['recommended_action'] == 'ROUTE'
correction = 'Correction: direct IP access fails too. My previous answer was wrong.'
turns.append(correction)
message, result = invoke([AIMessage(content=message.content), HumanMessage(content=correction)])
assert result['diagnosis_code'] is None and result['recommended_action'] == 'ESCALATE'
assert result['correction_pending_review']
evidence_id = result['correction_pending_review']['evidence_id']
final = client.get_ticket_details(tid)
assert any(e['evidence_id'] == evidence_id and e['source_type'] == 'USER_RESPONSE'
    and e['source_id'] == body['affected_person_id'] and e['observation'] == correction
    for e in final['evidence'])
assert final['status'] not in {'RESOLVED', 'CLOSED'}
assert final.get('owner_group_id') == created.get('owner_group_id')
message, resumed = invoke([HumanMessage(content='Investigate ' + tid)])
assert resumed['diagnosis_code'] is None and resumed['recommended_action'] == 'ESCALATE'
assert resumed['correction_pending_review']['evidence_id'] == evidence_id
report = {'passed': True, 'ticket_id': tid, 'correction_evidence_id': evidence_id,
    'diagnostic_result_id': result['diagnostic_result_id'],
    'diagnostic_result_version': result['diagnostic_result_version'],
    'text_only_followup': True, 'fresh_chat_resume': True, 'turns': turns}
(ROOT / 'docs/v62_live_correction_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
(ROOT / 'docs/v62_live_correction_attempt.json').write_text(json.dumps({
    'ticket_id': tid, 'stage': 'VERIFIED', 'passed': True}, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'turns'}), flush=True)

"""Create synthetic integration tickets and test native graph safety and continuation.

No assignment, resolution, global creation or notification is requested.
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
from wxo_langgraph.agent import create_agent, diagnostic_payload
from diagnostic_agent.backend_client import DiagnosticBackendClient
client = DiagnosticBackendClient()
reference = client.get_ticket_details('TST-0001')
scenarios = [
    ('access', 'Portal access denied', 'Email works but Portal denies access.', {}),
    ('application', 'Application save error', 'The application opens but save fails with error 512.', {}),
    ('endpoint', 'Disk full', 'My laptop reports storage full.', {}),
    ('arabic', 'مشكلة تسجيل الدخول', 'مش قادر ادخل على التطبيق', {'language': 'ar'}),
    ('critical', 'Application problem', 'Cannot access the application.', {'reported_priority': 1}),
    ('security', 'Suspicious login', 'Unrecognized login notification.', {'security_sensitive': True}),
    ('privileged', 'Admin access', 'Request requires privileged access.', {'privileged_access': True}),
]
report = []
for name, summary, description, extra in scenarios:
    entry = {'scenario': name}
    try:
        ticket = client.create_ticket({'action_id': 'matrix-' + uuid.uuid4().hex,
            'summary': 'Integration verification: ' + summary, 'description': description,
            'reported_by_id': reference['reported_by_id'], 'affected_person_id': reference['affected_person_id'], **extra})
        tid = ticket['ticket_id']
        entry['ticket_id'] = tid
        first = create_agent({}).compile().invoke({'messages': [HumanMessage(content='Investigate ' + tid)]})
        result = diagnostic_payload(first['messages'][-1])
        assert not result.get('error'), result.get('error')
        assert result.get('diagnostic_result_id'), 'Missing persisted diagnostic result'
        assert result['recommended_action'] != 'RESOLVE', 'Unexpected automatic resolution recommendation'
        if name in {'critical', 'security', 'privileged'}:
            assert result['recommended_action'] == 'ESCALATE'
            assert result.get('human_review', {}).get('review_id'), 'Mandatory review not persisted'
            followup = 'Thanks'
        else:
            followup = 'I do not know' if result.get('next_question') else 'Thanks'
        second = create_agent({}).compile().invoke({'messages': first['messages'] + [HumanMessage(content=followup)]})
        reply = diagnostic_payload(second['messages'][-1])
        assert not reply.get('error'), reply.get('error')
        assert client.get_ticket_details(tid)['status'] not in {'RESOLVED', 'CLOSED'}
        entry.update(result='PASS', initial_action=result['recommended_action'], followup_action=reply['recommended_action'])
    except Exception as exc:
        entry.update(result='FAIL', error=str(exc))
    report.append(entry)
    print(json.dumps(entry, ensure_ascii=False), flush=True)
target = root / 'docs' / 'live_regression_results.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
if any(entry['result'] != 'PASS' for entry in report):
    raise SystemExit(1)

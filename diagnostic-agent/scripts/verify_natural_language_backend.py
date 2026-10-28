"""Reproduce actual WXO reports and verify fresh text-only backend conversations."""
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
fixtures = json.loads((root / 'tests' / 'fixtures' / 'natural_language_reports.json').read_text(encoding='utf-8'))
report = []
for fixture in fixtures:
    tid = fixture['session']['ticket_id']
    original_ids = {e['evidence_id'] for e in fixture['session']['snapshot']['evidence']}
    # Empty native chat must resume backend records, not re-ask answered questions.
    output = create_agent({}).compile().invoke({'messages': [HumanMessage(content='Investigate ' + tid)]})
    message = output['messages'][-1]
    result = diagnostic_payload(message)
    assert not result.get('error'), result.get('error')
    assert not result.get('checkpoint_error'), result.get('checkpoint_error')
    assert set(result['evidence_ids']) == original_ids
    assert result['diagnostic_findings']['observations']
    assert result['diagnostic_findings']['leading_hypothesis']['supporting_evidence_ids']
    assert result['diagnosis_code'] is None
    assert result['recommended_action'] == 'ESCALATE'
    assert result['next_question'] is None
    assert result['completed_actions'] == []
    assert 'The available information isn’t enough' not in message.content
    report.append({'case': fixture['name'], 'phase': 'resume_actual_report', 'ticket_id': tid,
        'result': 'PASS', 'evidence_ids_preserved': True, 'reply': message.content})
    print(json.dumps({'case': fixture['name'], 'phase': 'resume_actual_report', 'result': 'PASS'}), flush=True)

    original = client.get_ticket_details(tid)
    payload = {key: original[key] for key in ('summary', 'description', 'reported_by_id', 'affected_person_id',
        'reported_priority', 'domain', 'category', 'language') if original.get(key) is not None}
    payload.update(action_id='natural-language-verification-' + uuid.uuid4().hex,
        summary=payload['summary'] + ' [verification]')
    created = client.create_ticket(payload)
    clone_id = created['ticket_id']
    messages = [HumanMessage(content='Investigate ' + clone_id)]
    output = create_agent({}).compile().invoke({'messages': messages})
    turns = [output['messages'][-1].content]
    answers = [e['value'] for e in fixture['session']['snapshot']['evidence'] if e['source'] == 'user_answer']
    consumed = 0
    while diagnostic_payload(output['messages'][-1]).get('next_question'):
        assert consumed < len(answers), 'Unexpected repeated/extra question'
        messages = [AIMessage(content=output['messages'][-1].content), HumanMessage(content=answers[consumed])]
        output = create_agent({}).compile().invoke({'messages': messages})
        consumed += 1
        turns.append(output['messages'][-1].content)
    result = diagnostic_payload(output['messages'][-1])
    assert not result.get('error'), result.get('error')
    assert not result.get('checkpoint_error'), result.get('checkpoint_error')
    assert result['diagnostic_findings']['leading_hypothesis']['supporting_evidence_ids']
    assert result['diagnosis_code'] is None
    assert result['recommended_action'] == 'ESCALATE'
    assert result['completed_actions'] == []
    assert client.get_ticket_details(clone_id)['status'] not in {'RESOLVED', 'CLOSED'}
    report.append({'case': fixture['name'], 'phase': 'fresh_text_only_chat', 'ticket_id': clone_id,
        'result': 'PASS', 'answers_consumed': consumed, 'turns': turns})
    print(json.dumps({'case': fixture['name'], 'phase': 'fresh_text_only_chat', 'result': 'PASS',
        'answers_consumed': consumed}), flush=True)
(root / 'docs' / 'natural_language_backend_verification.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

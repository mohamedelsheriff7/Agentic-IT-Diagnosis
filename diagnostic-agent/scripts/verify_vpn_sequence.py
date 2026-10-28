"""Verify investigate -> no -> explicit conflict handoff on the synthetic backend.

Writes answer evidence/audit checkpoints only; no assignment, global creation or resolution.
"""
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
root = Path(__file__).resolve().parents[1]
load_dotenv(root / '.env')
sys.path.insert(0, str(root))
from wxo_langgraph.agent import create_agent, diagnostic_payload
first = create_agent({}).compile().invoke({'messages': [HumanMessage(content='Investigate TST-0001')]})
initial = diagnostic_payload(first['messages'][-1])
assert initial.get('recommended_action') == 'ASK_MORE', initial.get('error')
second = create_agent({}).compile().invoke({'messages': first['messages'] + [HumanMessage(content='no')]})
result = diagnostic_payload(second['messages'][-1])
assert not result.get('error'), result.get('error')
assert result['recommended_action'] == 'ESCALATE'
assert 'VPN_OUTAGE' in result['remaining_candidates']
assert result['evidence_conflicts']
assert result['diagnosis_code'] is None
assert result['completed_actions'] == []
print(json.dumps({key: result.get(key) for key in ('ticket_id', 'recommended_action', 'outcome',
    'diagnostic_result_id', 'evidence_conflicts', 'remaining_candidates', 'rationale')}, ensure_ascii=False))

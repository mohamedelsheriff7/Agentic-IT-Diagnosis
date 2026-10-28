"""Investigate the reported synthetic case; records audit checkpoints only."""
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
load_dotenv(root / '.env')
from wxo_langgraph.agent import create_agent, diagnostic_payload
output = create_agent({}).compile().invoke({'messages': [HumanMessage(content='Investigate TST-0001')]})
result = diagnostic_payload(output['messages'][-1])
print(json.dumps({key: result.get(key) for key in ('ticket_id', 'recommended_action', 'outcome',
    'diagnostic_result_id', 'next_question', 'remaining_candidates', 'error')}, ensure_ascii=False))
assert not result.get('error')
assert result['recommended_action'] == 'ASK_MORE'
assert result['next_question']
assert result['confidence_basis']['historical_agreement'] == 'NOT_AVAILABLE'
assert 'VPN_OUTAGE' not in result['remaining_candidates']
assert result['completed_actions'] == []

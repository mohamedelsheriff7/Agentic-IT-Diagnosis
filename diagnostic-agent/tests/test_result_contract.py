"""Caller results survive both native graph and HTTP boundaries."""
import json
from langchain_core.messages import HumanMessage
from fastapi.testclient import TestClient
from diagnostic_agent.contract import build_contract
from wxo_langgraph.agent import create_agent, diagnostic_payload
import server


def test_http_graph_returns_machine_result_and_conversational_text(tmp_path, monkeypatch):
    monkeypatch.setenv('DIAGNOSTIC_SERVICE_API_KEY', 'contract-test-key')
    monkeypatch.setenv('DIAGNOSTIC_SESSIONS_DIR', str(tmp_path))
    # Isolate this test's checkpoint connection from other HTTP sessions.
    for name in ('langgraph_checkpointer', 'langgraph_connection', 'langgraph_apps'):
        if hasattr(server.app.state, name):
            delattr(server.app.state, name)
    ticket = {'ticket_id': 'CONTRACT-1', 'summary': 'Cannot sign in', 'description': 'Portal access denied'}
    with TestClient(server.app, headers={'X-API-Key': 'contract-test-key'}) as client:
        first = client.post('/langgraph/chat', json={'mode': 'local', 'session_id': 'contract-test',
            'message': json.dumps({'ticket_id': ticket['ticket_id'], 'ticket': ticket})})
        assert first.status_code == 200, first.text
        body = first.json()
        assert body['diagnostic_result']['ticket_id'] == ticket['ticket_id']
        assert body['diagnostic_result']['recommended_action'] == 'ASK_MORE'
        assert body['reply'] and not body['reply'].startswith('{')
        second = client.post('/langgraph/chat', json={'mode': 'local', 'session_id': 'contract-test',
            'message': 'Unknown, error code 512'})
        result = second.json()['diagnostic_result']
        assert result['evidence'][-1]['value'] == 'Unknown, error code 512'
        assert result['trace'] and result['completed_actions'] == []
    server.app.state.langgraph_connection.close()
    for name in ('langgraph_checkpointer', 'langgraph_connection', 'langgraph_apps'):
        delattr(server.app.state, name)


def test_missing_configuration_still_returns_machine_readable_result(monkeypatch):
    monkeypatch.delenv('DIAGNOSTIC_BACKEND_API_KEY', raising=False)
    output = create_agent({}).compile().invoke({'messages': [HumanMessage(content='Investigate INC-CONTRACT2')]})
    contract = output['diagnostic_result']
    assert contract == diagnostic_payload(output['messages'][-1])['diagnostic_result']
    assert contract['ticket_id'] == 'INC-CONTRACT2' and contract['error']
    assert contract['diagnosis'] is None and contract['completed_actions'] == []


def test_contract_does_not_expose_another_tickets_evidence():
    contract = build_contract({'ticket_id': 'NEW-TICKET'}, {'snapshot': {
        'ticket': {'ticket_id': 'OLD-TICKET'}, 'evidence': [{'evidence_id': 'OLD-EV'}], 'trace': ['old']}})
    assert contract['evidence'] == [] and contract['trace'] == []

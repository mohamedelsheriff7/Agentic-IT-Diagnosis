import json
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph
from wxo_langgraph.agent import create_agent, diagnostic_payload

def local_first(tid='LG-1', **flags):
    return HumanMessage(content=json.dumps({'ticket_id': tid, 'ticket': {
        'ticket_id': tid, 'summary': 'Cannot sign in', 'description': 'Portal access denied', **flags}}))

def test_factory_is_uncompiled_and_has_workflow_nodes():
    builder = create_agent({'configurable': {'mode': 'local'}})
    assert isinstance(builder, StateGraph)
    assert {'read_request', 'investigate', 'record_answer', 'confirm_resolution', 'respond'} <= set(builder.nodes)

def test_multiturn_survives_only_messages_and_fresh_factory():
    first = create_agent({'configurable': {'mode': 'local'}}).compile().invoke({'messages': [local_first()]})
    reply = diagnostic_payload(first['messages'][-1])
    assert reply['next_question']
    # Recreate the graph and discard every custom state field: native WXO preserves messages only.
    second = create_agent({'configurable': {'mode': 'local'}}).compile().invoke({
        'messages': first['messages'] + [HumanMessage(content='Unknown, error code 512')]})
    result = diagnostic_payload(second['messages'][-1])
    assert result['diagnostic_session']['snapshot']['evidence'][-1]['value'] == 'Unknown, error code 512'
    assert result['framework'] == 'langgraph'
    assert result['completed_actions'] == []

def test_isolation_and_mandatory_human_handling():
    graph = create_agent({'configurable': {'mode': 'local'}}).compile()
    critical = graph.invoke({'messages': [local_first('LG-P1', priority='1')]})
    assert diagnostic_payload(critical['messages'][-1])['recommended_action'] == 'ESCALATE'
    unrelated = graph.invoke({'messages': [HumanMessage(content='Hello')]})
    assert 'snapshot' not in diagnostic_payload(unrelated['messages'][-1])['diagnostic_session']

def test_native_connection_is_injected_not_read_from_user(monkeypatch):
    from wxo_langgraph import agent
    calls = []
    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', Client)
    monkeypatch.setattr(agent, 'investigate_ticket', lambda *a, **k: {'ticket_id': 'TST-0001', 'recommended_action': 'ASK_MORE'})
    graph = create_agent({'configurable': {'credentials': {'workstream_c_api_key': 'synthetic-test-key'}}}).compile()
    graph.invoke({'messages': [HumanMessage(content='Please investigate TST-0001')]})
    assert calls[0]['api_key'] == 'synthetic-test-key'

def test_no_inferred_resolution_confirmation():
    graph = create_agent({'configurable': {'mode': 'local'}}).compile()
    result = graph.invoke({'messages': [HumanMessage(content=json.dumps({
        'ticket_id': 'LG-1', 'operation': 'confirm_resolution', 'confirmed_by_user': True}))]})
    payload = diagnostic_payload(result['messages'][-1])
    assert payload['completed_actions'] == []
    assert 'cannot resolve' in payload['error']

def test_runtime_connection_injection_and_rotation(monkeypatch):
    from wxo_langgraph import agent
    monkeypatch.delenv('DIAGNOSTIC_BACKEND_API_KEY', raising=False)
    received = []
    class Client:
        def __init__(self, **kwargs):
            received.append(kwargs['api_key'])
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', Client)
    monkeypatch.setattr(agent, 'investigate_ticket', lambda *a, **k: {'ticket_id': 'TST-0001', 'recommended_action': 'ASK_MORE'})
    graph = create_agent({}).compile()
    for key in ('synthetic-key-one', 'synthetic-key-two'):
        output = graph.invoke({'messages': [HumanMessage(content='Investigate TST-0001')]},
            {'configurable': {'credentials': {'workstream_c_api_key': key}}})
        assert key not in output['messages'][-1].content
    assert received == ['synthetic-key-one', 'synthetic-key-two']

def test_missing_or_wrong_connection_reports_exact_binding(monkeypatch):
    monkeypatch.delenv('DIAGNOSTIC_BACKEND_API_KEY', raising=False)
    graph = create_agent({'configurable': {'credentials': {'unrelated_api_key': 'do-not-use'}}}).compile()
    output = graph.invoke({'messages': [HumanMessage(content='Investigate TST-0001')]})
    result = diagnostic_payload(output['messages'][-1])
    assert result['missing_configuration']['connection_app_id'] == 'isys_it_backend'
    assert 'isys_it_backend_api_key' in result['error']
    assert result['completed_actions'] == []
    assert 'do-not-use' not in output['messages'][-1].content

def test_actual_isys_connection_id_at_factory_and_runtime(monkeypatch):
    from wxo_langgraph import agent
    monkeypatch.delenv('DIAGNOSTIC_BACKEND_API_KEY', raising=False)
    received = []
    class Client:
        def __init__(self, **kwargs):
            received.append(kwargs['api_key'])
    monkeypatch.setattr(agent, 'DiagnosticBackendClient', Client)
    monkeypatch.setattr(agent, 'investigate_ticket', lambda *a, **k: {'ticket_id': 'TST-0001', 'recommended_action': 'ASK_MORE'})
    credential_config = {'configurable': {'credentials': {'isys_it_backend_api_key': 'synthetic-isys-key'}}}
    for factory_config, runtime_config in ((credential_config, {}), ({}, credential_config)):
        output = create_agent(factory_config).compile().invoke(
            {'messages': [HumanMessage(content='Investigate TST-0001')]}, runtime_config)
        assert 'error' not in diagnostic_payload(output['messages'][-1])
        assert 'synthetic-isys-key' not in output['messages'][-1].content
    assert received == ['synthetic-isys-key', 'synthetic-isys-key']

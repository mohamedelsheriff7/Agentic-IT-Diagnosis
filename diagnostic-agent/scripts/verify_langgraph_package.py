"""Validate ZIP layout and invoke its factory in a clean subprocess."""
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import yaml
import ast
import base64
import io

root = Path(__file__).resolve().parents[1]
package = root / 'dist' / 'isys-diagnostic-langgraph-v6.8.3.zip'
with zipfile.ZipFile(package) as archive:
    names = archive.namelist()
    assert {'agent.yaml', 'agent.py', 'requirements.txt'} <= set(names)
    assert not any(Path(n).name in {'.env', 'workstream.db'} or '/venv/' in n or '/.venv/' in n for n in names)
    assert not any('evaluation' in n or 'test_tickets' in n or 'ground_truth' in n for n in names)
    definition = yaml.safe_load(archive.read('agent.yaml'))
    assert definition['kind'] == 'agent' and definition['spec_version'] == 'v1'
    assert definition['deployment']['code_bundle']['entrypoint'] == 'agent:create_agent'
    tree = ast.parse(archive.read('agent.py').decode('utf-8'))
    encoded = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == '_EMBEDDED_CORE' for t in n.targets))
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as core:
        resources = core.namelist()
        assert 'adk-project/agents/diagnostic_agent/__init__.py' in resources
        assert 'adk-project/knowledge/reviewed/diagnostic_articles.json' in resources
        articles = json.loads(core.read('adk-project/knowledge/reviewed/diagnostic_articles.json'))
        expected = json.loads((root / 'docs/backend_kb001_reference.json').read_text(encoding='utf-8'))
        assert next(a for a in articles if a['article_id'] == 'KB-001') == expected
        references = json.loads((root / 'docs/backend_article_reference.json').read_text(encoding='utf-8'))
        by_id = {a['article_id']: a for a in articles}
        assert len(articles) == 38
        assert len([a for a in articles if a.get('guided_self_service')]) == 12
        assert all(by_id[a['article_id']] == a for a in references)
        assert not any(Path(n).name == '.env' or 'evaluation' in n or 'ground_truth' in n for n in resources)
    with tempfile.TemporaryDirectory(prefix='verify-native-', dir=root / 'dist') as directory:
        entrypoint = Path(directory) / 'relocated-entrypoint'
        entrypoint.mkdir()
        working = Path(directory) / 'unrelated-working-directory'
        working.mkdir()
        # Deliberately provide ONLY agent.py; no sibling package/data directories.
        isolated_agent = entrypoint / 'agent.py'
        isolated_agent.write_bytes(archive.read('agent.py'))
        code = '''
import asyncio, json, sys, importlib.util
assert importlib.util.find_spec('diagnostic_agent') is None
spec = importlib.util.spec_from_file_location('relocated_wxo_agent', sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
create_agent = module.create_agent
diagnostic_payload = module.diagnostic_payload
from langgraph.graph import StateGraph
from langchain_core.messages import HumanMessage
builder = create_agent({'configurable': {'mode': 'local'}})
assert isinstance(builder, StateGraph)
compiled = builder.compile()
ticket = {'ticket_id':'PORTABLE-1','summary':'Cannot sign in','description':'Portal access denied'}
first = compiled.invoke({'messages':[HumanMessage(content=json.dumps({'ticket_id':'PORTABLE-1','ticket':ticket}))]})
payload = diagnostic_payload(first['messages'][-1])
assert payload['next_question']
assert not first['messages'][-1].content.startswith('{')
second = create_agent({'configurable': {'mode':'local'}}).compile().invoke({'messages':first['messages']+[HumanMessage(content='Unknown error 512')]})
assert diagnostic_payload(second['messages'][-1])['diagnostic_session']['snapshot']['evidence'][-1]['value'] == 'Unknown error 512'
printer = {'ticket_id':'OBS-PRINT','summary':'Printer offline','description':'Office printer offline'}
chat = compiled.invoke({'messages':[HumanMessage(content=json.dumps({'ticket_id':'OBS-PRINT','ticket':printer}))]})
for answer in ('Everyone using that printer is affected.', 'Other users cannot reach the printer either.'):
    chat = create_agent({'configurable': {'mode':'local'}}).compile().invoke({'messages':chat['messages']+[HumanMessage(content=answer)]})
assert 'Other users cannot reach the printer' in chat['messages'][-1].content
assert diagnostic_payload(chat['messages'][-1])['diagnostic_findings']['leading_hypothesis']['supporting_evidence_ids']
with open(module.ROOT / 'adk-project/knowledge/reviewed/diagnostic_articles.json', encoding='utf-8') as source:
    guide_articles = [a for a in json.load(source) if a.get('guided_self_service')]
assert len(guide_articles) == 12
for guide in guide_articles:
    ticket = {'ticket_id':'GUIDE-' + guide['article_id'], 'summary':guide['title'], 'description':guide['symptoms_en'][0]}
    chat = compiled.invoke({'messages':[HumanMessage(content=json.dumps({'ticket_id':ticket['ticket_id'],'ticket':ticket}))]})
    payload = diagnostic_payload(chat['messages'][-1])
    plans = {p['article_id']:p for p in payload['available_self_service_guides']}
    assert guide['article_id'] in plans
    assert plans[guide['article_id']]['authorizes_ticket_resolution'] is False
    assert payload['completed_actions'] == []
from diagnostic_agent.session_store import _state_from_dict
from diagnostic_agent.engine import submit_answer
from diagnostic_agent.conversation import render_reply
with open(sys.argv[2], encoding='utf-8') as fixture:
    saved = json.load(fixture)
legacy = _state_from_dict(saved['session']['snapshot'])
submit_answer(legacy, 'No, colleagues at the same site cannot connect either.', 'PORTABLE-PEERS-FAIL')
assert legacy.status == 'escalated' and legacy.final_diagnosis is None
assert any(c.diagnosis_id == 'VPN_OUTAGE' for c in legacy.candidates)
assert 'Supervisor' in legacy.rationale
assert 'Supervisor' in render_reply(module._public_result(legacy), {'snapshot': module._state_to_dict(legacy)})
async def stream_test():
    chunks = [c async for c in compiled.astream({'messages':[HumanMessage(content='Hello')]}, stream_mode='updates')]
    assert any('respond' in c for c in chunks)
asyncio.run(stream_test())
print(json.dumps({'single_file_relocated_factory':'passed','message_only_resume':'passed','natural_observation_conversation':'passed','self_service_guides_retrieved':len(guide_articles),'legacy_shared_scope_recovery':'passed','async_streaming':'passed'}))
'''
        environment = {k: v for k, v in os.environ.items() if not k.startswith(('DIAGNOSTIC_', 'LANGSMITH_'))}
        check = subprocess.run([sys.executable, '-I', '-c', code, str(isolated_agent),
            str(root / 'docs/CHK-f6b3cd70a0c64c9b.json')], cwd=working, env=environment,
            capture_output=True, text=True, timeout=45)
        if check.returncode:
            print(check.stdout)
            print(check.stderr)
            raise SystemExit(check.returncode)
        print(check.stdout.strip())
print(json.dumps({'zip_layout': 'passed', 'credential_files_excluded': True, 'files': len(names), 'embedded_resources': len(resources)}))

"""Reproduce v6.7's missing taxonomy and test v6.8 in the same warm worker.

Runs in a clean subprocess with its own owned temporary cache. No backend calls.
"""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CODE = r'''
import gc, importlib, importlib.util, json, shutil, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from langchain_core.messages import HumanMessage
owned = Path(sys.argv[3]).resolve()
owned.mkdir()
tempfile.tempdir = str(owned)
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
def clean(root):
    root = root.resolve()
    assert owned in root.parents, 'Refuse cleanup outside owned test cache'
    shutil.rmtree(root)
old = load(sys.argv[1], 'runtime_v67')
assert owned in old.ROOT.resolve().parents
old._CORE_DIRECTORY.cleanup()
old_again = load(sys.argv[1], 'runtime_v67_again')
engine_old = importlib.import_module('diagnostic_agent.engine')
models_old = importlib.import_module('diagnostic_agent.models')
try:
    engine_old._introduce_reported_hypotheses(models_old.DiagnosticState(
        ticket=models_old.TicketInput('REPRO', 'Unknown', 'Unknown')),
        models_old.Evidence('EV-OLD', 'Reported lock', 'Account locked', 'user_answer', supports=['ACCOUNT_LOCKED']),
        {'facts': {'account_message': 'LOCKED'}})
except FileNotFoundError as exc:
    assert Path(exc.filename).name == 'taxonomy.json'
else:
    raise AssertionError('Expected exact v6.7 failure')
new = load(sys.argv[2], 'runtime_v68')
assert new.investigate_ticket.__module__.startswith(new._CORE_PACKAGE + '.')
assert new.investigate_ticket.__module__ != old.investigate_ticket.__module__
engine = importlib.import_module(new._CORE_PACKAGE + '.engine')
models = importlib.import_module(new._CORE_PACKAGE + '.models')
messages = []
for index in range(5):
    # Compile first, then mimic host cleanup before invocation.
    graph = new.create_agent({'configurable': {'mode': 'local'}}).compile()
    clean(new.ROOT)
    ticket = {'ticket_id': 'RUNTIME-' + str(index), 'summary': 'Unclear problem', 'description': 'Something is wrong'}
    first = graph.invoke({'messages': [HumanMessage(content=json.dumps({'ticket_id': ticket['ticket_id'], 'ticket': ticket}))]})
    assert new.diagnostic_payload(first['messages'][-1])['next_question']
    clean(new.ROOT)
    second = graph.invoke({'messages': first['messages'] + [HumanMessage(content='The screen says my account is locked.')]})
    assert not new.diagnostic_payload(second['messages'][-1]).get('error')
    # Exercise exactly the newly introduced-hypothesis taxonomy read.
    engine._introduce_reported_hypotheses(models.DiagnosticState(ticket=models.TicketInput('NEW', 'Unknown', 'Unknown')),
        models.Evidence('EV-NEW', 'Reported lock', 'Account locked', 'user_answer', supports=['ACCOUNT_LOCKED']),
        {'facts': {'account_message': 'LOCKED'}})
    alias = 'runtime_v68_repeat_' + str(index)
    reloaded = load(sys.argv[2], alias)
    assert reloaded.ROOT == new.ROOT
    assert reloaded.investigate_ticket is new.investigate_ticket
    del sys.modules[alias]
    del reloaded
    gc.collect()
    assert (new.ROOT / 'adk-project/knowledge/taxonomy.json').exists()
# Restore corrupted immutable content and check parallel atomic restoration.
taxonomy = new.ROOT / 'adk-project/knowledge/taxonomy.json'
taxonomy.write_text('broken', encoding='utf-8')
with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(lambda _: new.create_agent({'configurable': {'mode': 'local'}}), range(8)))
assert isinstance(json.loads(taxonomy.read_text(encoding='utf-8')), list)
print(json.dumps({'v67_exact_error_reproduced': True, 'warm_version_isolation': True,
    'cleanup_and_repeat_cycles_passed': 5, 'garbage_collection_safe': True,
    'corrupt_resource_restored': True, 'concurrent_factories_passed': 8}))
'''


def main():
    with tempfile.TemporaryDirectory(prefix='v68-runtime-', dir=ROOT / 'dist') as directory:
        directory = Path(directory)
        paths = []
        for version in ('6.7', '6.8'):
            target = directory / ('agent_' + version.replace('.', '_') + '.py')
            with zipfile.ZipFile(ROOT / ('dist/isys-diagnostic-langgraph-v' + version + '.zip')) as archive:
                target.write_bytes(archive.read('agent.py'))
            paths.append(str(target))
        environment = {k: v for k, v in os.environ.items() if not k.startswith(('DIAGNOSTIC_', 'LANGSMITH_'))}
        result = subprocess.run([sys.executable, '-I', '-c', CODE, *paths, str(directory / 'cache')],
            cwd=directory, env=environment, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        report = json.loads(result.stdout)
        report['package_sha256'] = hashlib.sha256((ROOT / 'dist/isys-diagnostic-langgraph-v6.8.zip').read_bytes()).hexdigest()
        (ROOT / 'docs/v68_runtime_results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report))


if __name__ == '__main__':
    main()

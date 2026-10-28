"""Build a secret-free native WXO import ZIP from maintained project sources."""
from pathlib import Path
import zipfile
import json
import importlib.metadata
import io
import base64

root = Path(__file__).resolve().parents[1]
output = root / 'dist' / 'isys-diagnostic-langgraph-v6.8.3.zip'
output.parent.mkdir(exist_ok=True)
files = {}
for path in (root / 'adk-project' / 'agents' / 'diagnostic_agent').rglob('*'):
    if path.suffix in {'.py', '.md'} and '__pycache__' not in path.parts:
        files[path] = path.relative_to(root).as_posix()
for name in ('historical_tickets.json', 'taxonomy.json', 'reviewed/diagnostic_articles.json', 'reviewed/approval_register.json'):
    path = root / 'adk-project' / 'knowledge' / name
    files[path] = path.relative_to(root).as_posix()
versions = {name: importlib.metadata.version(name) for name in ('langgraph', 'langchain-core', 'langgraph-checkpoint-sqlite')}
requirements = '\n'.join(name + '==' + version for name, version in versions.items()) + '\n'
(root / 'wxo_langgraph' / 'requirements.txt').write_text(requirements, encoding='utf-8')
embedded = io.BytesIO()
with zipfile.ZipFile(embedded, 'w', zipfile.ZIP_DEFLATED) as core:
    for path, destination in sorted(files.items(), key=lambda pair: pair[1]):
        core.write(path, destination)
source = (root / 'wxo_langgraph' / 'agent.py').read_text(encoding='utf-8')
marker = "_EMBEDDED_CORE = ''"
assert source.count(marker) == 1
source = source.replace(marker, '_EMBEDDED_CORE = ' + repr(base64.b64encode(embedded.getvalue()).decode('ascii')), 1)
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('agent.py', source)
    archive.write(root / 'wxo_langgraph' / 'agent.yaml', 'agent.yaml')
    archive.writestr('requirements.txt', requirements)
print(json.dumps({'package': str(output), 'root_files': 3, 'embedded_resources': len(files), 'versions': versions}))

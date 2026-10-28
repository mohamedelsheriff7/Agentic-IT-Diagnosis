"""Mirror the live backend's KB-001 locally; this script makes no backend writes."""
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT / 'adk-project/agents'))
from diagnostic_agent.backend_client import DiagnosticBackendClient

rows = DiagnosticBackendClient(timeout=15).search_diagnostic_knowledge({'query': 'password expired', 'limit': 5})['results']
matches = [a for a in rows if a.get('article_id') == 'KB-001']
if len(matches) != 1:
    raise ValueError('Expected exactly one authoritative backend KB-001.')
backend = matches[0]
assert backend['diagnosis_code'] == 'PASSWORD_EXPIRED'
assert backend['approved'] is True and backend['agent_resolvable'] is True
assert backend['resolution_steps'] and all(s['level'] == 'SELF_SERVICE' for s in backend['resolution_steps'])
assert {c['field'] for c in backend['resolution_conditions']} >= {'password_expired', 'enabled', 'locked', 'mfa_locked'}

directory = ROOT / 'adk-project/knowledge/reviewed'
article_path = directory / 'diagnostic_articles.json'
articles = json.loads(article_path.read_text(encoding='utf-8'))
position = next(i for i, a in enumerate(articles) if a['article_id'] == 'KB-001')
previous = deepcopy(articles[position])
articles[position] = deepcopy(backend)
digest = hashlib.sha256(json.dumps(backend, ensure_ascii=False, sort_keys=True,
    separators=(',', ':')).encode('utf-8')).hexdigest()
register_path = directory / 'approval_register.json'
register = json.loads(register_path.read_text(encoding='utf-8'))
old_approval = next(a for a in register['article_approvals'] if a['article_id'] == 'KB-001')
if old_approval['article_sha256'] != digest:
    register.setdefault('approval_history', []).append({
        'decision': 'Superseded local KB-001 wording by exact backend mirror at owner request',
        'article_approvals': [deepcopy(old_approval)]})
    old_approval.update(version=backend['version'], article_sha256=digest,
        authorization='can u make KB-001 alligned with the backend not the opposite',
        scope='Exact live-backend KB-001 mirror for conditional guided self-service; all evidence, human restrictions, user confirmation and backend success remain required.',
        changed_fields=[k for k in sorted(set(previous) | set(backend)) if previous.get(k) != backend.get(k)],
        deployment_status='NOT_DEPLOYED')
register['backend_alignment'] = {'article_id': 'KB-001', 'backend_article_version': backend['version'],
    'article_sha256': digest, 'mode': 'EXACT_BACKEND_MIRROR', 'verified_on': '2026-10-25',
    'backend_modified': False}
register['note'] = ('All 26 articles remain approved for scoped synthetic guidance. KB-001 is an exact mirror of live backend version '
    + str(backend['version']) + '; other reviewed articles retain their own versions. '
    'Only KB-001 is an agent-resolution candidate. Runtime workflow completion and deployment are separate. Policy activation remains pending.')
article_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
register_path.write_text(json.dumps(register, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'docs/backend_kb001_reference.json').write_text(json.dumps(backend, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'docs/kb001_backend_alignment.json').write_text(json.dumps({
    'article_id': 'KB-001', 'previous_local_version': previous['version'],
    'backend_version': backend['version'], 'local_equals_backend': articles[position] == backend,
    'backend_modified': False, 'article_sha256': digest,
    'changed_fields': [k for k in sorted(set(previous) | set(backend)) if previous.get(k) != backend.get(k)],
    'step_ids': [s['step_id'] for s in backend['resolution_steps']],
    'conditions': backend['resolution_conditions']}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'article_id': 'KB-001', 'backend_version': backend['version'], 'exact_mirror': True,
    'step_ids': [s['step_id'] for s in backend['resolution_steps']], 'backend_modified': False}))

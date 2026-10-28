"""Align local definitions to a read-only live reference; retain unavailable guidance."""
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

directory = ROOT / 'adk-project/knowledge/reviewed'
path = directory / 'diagnostic_articles.json'
articles = json.loads(path.read_text(encoding='utf-8'))
reference_path = ROOT / 'docs/backend_article_reference.json'
reference = json.loads(reference_path.read_text(encoding='utf-8'))
by_id = {a['article_id']: a for a in reference}
client = DiagnosticBackendClient(timeout=15)
searches = []
for article in articles:
    identifier = article['article_id']
    if identifier in by_id:
        continue
    for query in (article['diagnosis_code'], ' '.join(article['symptoms_en'])):
        results = client.search_diagnostic_knowledge({'query': query, 'limit': 50})['results']
        match = next((a for a in results if a['article_id'] == identifier), None)
        searches.append({'article_id': identifier, 'query': query, 'matched': bool(match)})
        if match:
            by_id[identifier] = match
            break

archive_path = ROOT / 'docs/pre_backend_alignment_articles.json'
if not archive_path.exists():
    archive_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
register_path = directory / 'approval_register.json'
register = json.loads(register_path.read_text(encoding='utf-8'))
old_approvals = deepcopy(register['article_approvals'])
approvals = {a['article_id']: a for a in register['article_approvals']}
changes = []
for index, article in enumerate(articles):
    identifier = article['article_id']
    backend = by_id.get(identifier)
    if backend:
        if backend['diagnosis_code'] != article['diagnosis_code']:
            raise ValueError('Diagnosis-code mismatch for ' + identifier)
        assert backend['approved'] is True
        articles[index] = deepcopy(backend)
        digest = hashlib.sha256(json.dumps(backend, sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')).hexdigest()
        fields = [k for k in sorted(set(article) | set(backend)) if article.get(k) != backend.get(k)]
        approvals[identifier].update(version=backend['version'], article_sha256=digest,
            authorization='yes do this (align the remaining articles to the live backend)',
            scope='Exact approved live-backend definition. Diagnostic evidence, agent_resolvable, human restrictions and success confirmation remain separately enforced.',
            changed_fields=fields, backend_match='EXACT_BACKEND_MIRROR', deployment_status='NOT_DEPLOYED')
        changes.append({'article_id': identifier, 'diagnosis_code': backend['diagnosis_code'],
            'status': 'EXACT_BACKEND_MIRROR', 'local_version': backend['version'],
            'changed_fields': fields, 'agent_resolvable': backend['agent_resolvable'],
            'step_ids': [s['step_id'] for s in backend['resolution_steps']], 'article_sha256': digest})
    else:
        assert article['agent_resolvable'] is False
        approvals[identifier].update(backend_match='NO_APPROVED_BACKEND_MATCH',
            scope='Owner-approved local diagnostic guidance and human handoff only; no backend article reference or agent resolution authorized.')
        changes.append({'article_id': identifier, 'diagnosis_code': article['diagnosis_code'],
            'status': 'NO_APPROVED_BACKEND_MATCH', 'local_version': article['version'],
            'agent_resolvable': False, 'changed_fields': [],
            'note': 'Not returned by focused approved-knowledge searches; also absent from supplied backend article file. Not proof that no unapproved live record exists.'})

mirrored = [a['article_id'] for a in changes if a['status'] == 'EXACT_BACKEND_MIRROR']
unavailable = [a['article_id'] for a in changes if a['status'] != 'EXACT_BACKEND_MIRROR']
if old_approvals != [approvals[a['article_id']] for a in articles]:
    register.setdefault('approval_history', []).append({
        'decision': 'Local reviewed definitions superseded by backend-directed alignment; original guidance archived',
        'article_approvals': old_approvals})
register['article_approvals'] = [approvals[a['article_id']] for a in articles]
register['backend_alignment_all'] = {'mode': 'BACKEND_AUTHORITATIVE', 'verified_on': '2026-10-25',
    'exact_mirror_ids': mirrored, 'unavailable_article_ids': unavailable, 'backend_modified': False}
register['note'] = ('Owner-approved diagnostic knowledge: ' + str(len(mirrored)) + ' exact live-backend definitions and '
    + str(len(unavailable)) + ' local-only diagnostic guidance articles. Only KB-001 is an agent-resolution candidate. '
    'Backend unchanged; article alignment does not activate policy or complete the guided resolution workflow.')
path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
register_path.write_text(json.dumps(register, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
reference_path.write_text(json.dumps([by_id[k] for k in sorted(by_id)], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
report = {'backend_modified': False, 'exact_mirrors': mirrored, 'unavailable': unavailable,
    'additional_missing_article_searches': searches, 'articles': changes}
(ROOT / 'docs/backend_article_alignment.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'exact_mirrors': len(mirrored), 'remaining_25_aligned': len([i for i in mirrored if i != 'KB-001']),
    'unavailable': unavailable, 'backend_modified': False}))

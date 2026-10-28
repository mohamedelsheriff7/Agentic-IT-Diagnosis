"""Approval integrity and limits for the owner-reviewed synthetic knowledge set."""
import hashlib
import json
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[1] / 'adk-project/knowledge/reviewed'


def test_each_approved_article_matches_recorded_version_and_content_hash():
    articles = json.loads((DIRECTORY / 'diagnostic_articles.json').read_text(encoding='utf-8'))
    register = json.loads((DIRECTORY / 'approval_register.json').read_text(encoding='utf-8'))
    approvals = {row['article_id']: row for row in register['article_approvals']}
    assert len(articles) == len(approvals) == 38
    assert {a['article_id'] for a in articles if a['approved']} == set(register['approved_article_ids'])
    for article in articles:
        digest = hashlib.sha256(json.dumps(article, sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')).hexdigest()
        assert article['version'] == approvals[article['article_id']]['version']
        assert digest == approvals[article['article_id']]['article_sha256']


def test_article_approval_does_not_activate_policy_or_specialist_resolution():
    articles = json.loads((DIRECTORY / 'diagnostic_articles.json').read_text(encoding='utf-8'))
    register = json.loads((DIRECTORY / 'approval_register.json').read_text(encoding='utf-8'))
    assert register['policy_approved'] is False
    assert [a['article_id'] for a in articles if a['agent_resolvable']] == ['KB-001']
    for article in articles:
        if any(s['level'] == 'SPECIALIST' for s in article['resolution_steps']):
            assert not article['agent_resolvable']
        if article['agent_resolvable']:
            assert article['resolution_conditions']
    assert all(a['deployment_status'] == 'NOT_DEPLOYED' for a in register['article_approvals'])


def test_kb001_exactly_matches_the_verified_backend_contract():
    reference = json.loads((DIRECTORY.parents[2] / 'docs/backend_kb001_reference.json').read_text(encoding='utf-8'))
    articles = json.loads((DIRECTORY / 'diagnostic_articles.json').read_text(encoding='utf-8'))
    actual = next(a for a in articles if a['article_id'] == 'KB-001')
    assert actual == reference
    assert actual['version'] == 1
    assert [s['step_id'] for s in actual['resolution_steps']] == ['PASSWORD_EXPIRED-1']
    assert {c['field']: c['equals'] for c in actual['resolution_conditions']} == {
        'password_expired': 'TRUE', 'enabled': 'TRUE', 'locked': 'FALSE', 'mfa_locked': 'FALSE'}


def test_all_available_backend_articles_are_exact_mirrors_and_missing_remain_guidance_only():
    root = DIRECTORY.parents[2]
    reference = json.loads((root / 'docs/backend_article_reference.json').read_text(encoding='utf-8'))
    articles = {a['article_id']: a for a in json.loads((DIRECTORY / 'diagnostic_articles.json').read_text(encoding='utf-8'))}
    report = json.loads((root / 'docs/backend_article_alignment.json').read_text(encoding='utf-8'))
    assert len(reference) == 24
    assert all(articles[a['article_id']] == a for a in reference)
    assert set(report['unavailable']) == {'KB-025', 'KB-026'}
    assert report['backend_modified'] is False
    assert all(articles[identifier]['agent_resolvable'] is False for identifier in report['unavailable'])


def test_candidate_scope_is_applied_before_retrieval_limit(tmp_path):
    from diagnostic_agent.knowledge import search_articles
    rows = [{'article_id': 'DISTRACTOR-' + str(i), 'diagnosis_code': 'APP_ERROR',
        'approved': True, 'symptoms_en': ['internal names fail direct access']} for i in range(8)]
    rows.append({'article_id': 'DNS-MATCH', 'diagnosis_code': 'DNS_FAILURE',
        'approved': True, 'symptoms_en': ['names fail']})
    path = tmp_path / 'articles.json'
    path.write_text(json.dumps(rows), encoding='utf-8')
    matches = search_articles('internal names fail direct access', path=path, limit=1,
        diagnosis_codes={'DNS_FAILURE'})
    assert [m['article_id'] for m in matches] == ['DNS-MATCH']

"""Owner-requested local self-service guidance remains retrievable and bounded."""
import json
from pathlib import Path
import pytest
from diagnostic_agent.knowledge import search_articles
from diagnostic_agent.engine import start_investigation
from diagnostic_agent.models import TicketInput
from diagnostic_agent.standalone import _public_result

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'adk-project/knowledge/reviewed/diagnostic_articles.json'
MANIFEST = json.loads((ROOT / 'docs/self_service_article_manifest.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('scenario', MANIFEST, ids=[a['scenario_code'] for a in MANIFEST])
def test_new_guidance_retrieved_and_exposed_without_claiming_resolution(scenario):
    results = search_articles(scenario['example_report'], path=PATH,
        diagnosis_codes={scenario['diagnosis_code']}, limit=3)
    assert scenario['article_id'] in {a['article_id'] for a in results}
    state = start_investigation(TicketInput('GUIDE-' + scenario['article_id'],
        scenario['title'], scenario['example_report'], metadata={'diagnostic_review_mode': True}), articles_path=PATH)
    output = _public_result(state)
    plans = {g['article_id']: g for g in output['available_self_service_guides']}
    assert scenario['article_id'] in plans
    plan = plans[scenario['article_id']]
    assert plan['steps'] and plan['eligibility_evidence'] and plan['success_criteria'] and plan['stop_conditions']
    assert plan['backend_registered'] is False
    assert plan['authorizes_ticket_resolution'] is False
    assert plan['execution_status'] == 'NOT_EXECUTED'
    assert output['completed_actions'] == []
    assert output['recommended_action'] != 'RESOLVE'


def test_all_new_guides_preserve_backend_contracts_and_safe_boundaries():
    articles = {a['article_id']: a for a in json.loads(PATH.read_text(encoding='utf-8'))}
    assert len(MANIFEST) == 12
    for entry in MANIFEST:
        article = articles[entry['article_id']]
        assert article['approved'] is True and article['guided_self_service'] is True
        assert article['backend_reference'] is False and article['agent_resolvable'] is False
        assert article['resolution_conditions'] == []
        assert all(s['level'] == 'SELF_SERVICE' for s in article['resolution_steps'])
        assert len({s['step_id'] for s in article['resolution_steps']}) == len(article['resolution_steps'])
        assert article['source_urls']
    references = json.loads((ROOT / 'docs/backend_article_reference.json').read_text(encoding='utf-8'))
    assert all(articles[a['article_id']] == a for a in references)


@pytest.mark.parametrize('query', [
    'VPN client connection configuration error on this device',
    'Internal hostnames fail but direct IP works',
    'Cannot sign in because password expired',
])
def test_generic_connection_terms_do_not_introduce_endpoint_guides(query):
    results = search_articles(query, path=PATH, limit=50)
    assert not any(r['article'].get('guided_self_service') for r in results)


def test_named_arabic_topic_can_retrieve_matching_guide():
    results = search_articles('البلوتوث لا يعمل', path=PATH, limit=50)
    assert 'KB-036' in {r['article_id'] for r in results}
    assert 'KB-037' not in {r['article_id'] for r in results}

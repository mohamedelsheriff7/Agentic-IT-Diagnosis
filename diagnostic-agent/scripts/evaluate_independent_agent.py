"""Evaluate separate Workstream A tickets; labels are used only by the harness.

Recorded tool fixtures and topic-matched scripted user answers are simulator
inputs, not agent knowledge. Does not contact or mutate the live backend.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
import zipfile
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--package', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
temporary = tempfile.TemporaryDirectory(prefix='independent-eval-', dir=ROOT / 'dist')
entry = Path(temporary.name) / 'agent.py'
with zipfile.ZipFile(ROOT / args.package) as package:
    entry.write_bytes(package.read('agent.py'))
spec = importlib.util.spec_from_file_location('evaluated_agent', entry)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)
from diagnostic_agent.integrated import investigate_ticket, submit_answer_and_continue
from diagnostic_agent.answers import question_family

dataset = ROOT.parents[1] / 'Workstream A'
tickets_path = dataset / 'TestSet_Tickets.json'
truth_path = dataset / 'ground_truth.json'
tickets = json.loads(tickets_path.read_text(encoding='utf-8-sig'))
truth = {r['ticket_id']: r for r in json.loads(truth_path.read_text(encoding='utf-8-sig'))}
taxonomy = {a['diagnosis_code']: a['resolver_group_id'] for a in json.loads(
    (agent.ROOT / 'adk-project/knowledge/taxonomy.json').read_text(encoding='utf-8'))}
articles = agent.ROOT / 'adk-project/knowledge/reviewed/diagnostic_articles.json'
history = agent.ROOT / 'adk-project/knowledge/historical_tickets.json'


class Simulator:
    def __init__(self, ticket, fixtures):
        self.ticket = ticket
        self.fixtures = fixtures
        self.serial = 0
    def get_ticket_details(self, tid):
        return deepcopy(self.ticket)
    def search_similar_tickets(self, payload):
        return {'results': []}
    def search_diagnostic_knowledge(self, payload):
        return {'results': []}
    def check(self, name):
        self.serial += 1
        result = deepcopy(self.fixtures.get(name, {}))
        if not result:
            result = {'state': 'UNKNOWN'} if name == 'check_service_health' else {'status': 'UNKNOWN'}
        return {**result, 'evidence_id': 'SIM-TOOL-' + str(self.serial)}
    def check_account_status(self, payload):
        return self.check('check_account_status')
    def check_application_entitlement(self, payload):
        return self.check('check_application_entitlement')
    def check_service_health(self, payload):
        return self.check('check_service_health')
    def add_worklog_entry(self, tid, payload):
        self.serial += 1
        return {'worklog_id': 'SIM-WL-' + str(self.serial),
            'evidence_ids': ['SIM-ANSWER-' + str(self.serial)] if payload.get('evidence') else []}
    def record_diagnostic_result(self, tid, payload):
        self.serial += 1
        return {'diagnostic_result_id': 'SIM-DR-' + str(self.serial), 'version': self.serial}
    def request_human_review(self, tid, payload):
        return {'review_id': 'SIM-REVIEW', 'state': 'REQUESTED'}
    def find_open_global_tickets(self, payload):
        return {'results': []}
    def count_recent_tickets(self, payload):
        now = datetime.fromisoformat(self.ticket['reported_at'].replace('Z', '+00:00'))
        matching = []
        for t in tickets:
            moment = datetime.fromisoformat(t['reported_at'].replace('Z', '+00:00'))
            if now - timedelta(minutes=30) <= moment <= now and all(
                not payload.get(key) or t.get(key) == payload[key]
                for key in ('category', 'configuration_item_id', 'location_id')):
                matching.append(t['ticket_id'])
        return {'count': len(matching), 'matching_ticket_ids': matching}


def scripted_answer(question, available, used):
    from evaluation_user import scripted_answer as answer_for_topic
    return answer_for_topic(question, available, used, question_family)


results = []
for ticket in tickets:
    label = truth[ticket['ticket_id']]
    backend = Simulator(ticket, label.get('required_fixtures', {}))
    session = {'mode': 'backend'}
    store = agent.MessageSessionStore(session)
    asked = []
    used = set()
    try:
        result = investigate_ticket(backend, ticket['ticket_id'], store=store,
            articles_path=articles, history_path=history, diagnostic_review_mode=True)
        initial_diagnosis = result.get('diagnosis_code')
        for step in range(8):
            if result.get('recommended_action') != 'ASK_MORE' or not result.get('next_question'):
                break
            question = result['next_question']
            if any(a['question'] == question and a['topic'] is None for a in asked):
                break
            answer, topic = scripted_answer(question, label.get('discoverable_information', []), used)
            before = len(result.get('eliminated_diagnoses', []))
            result = submit_answer_and_continue(backend, ticket['ticket_id'], answer,
                'SIM-REQUEST-' + str(step), store, articles_path=articles, history_path=history, diagnostic_review_mode=True)
            asked.append({'question': question, 'topic': topic, 'answer': answer,
                'eliminated_more': len(result.get('eliminated_diagnoses', [])) > before})
        codes = ([result['diagnosis_code']] if result.get('diagnosis_code') else []) + [
            c['diagnosis_id'] for c in result.get('candidate_rankings', [])]
        groups = list(dict.fromkeys(taxonomy[c] for c in codes if c in taxonomy))
        results.append({'ticket_id': ticket['ticket_id'], 'language': ticket.get('language'),
            'expected_diagnosis': label['expected_diagnosis_code'], 'actual_diagnosis': result.get('diagnosis_code'),
            'diagnosis_correct': result.get('diagnosis_code') == label['expected_diagnosis_code'],
            'recommended_action': result.get('recommended_action'), 'outcome': result.get('outcome'),
            'confidence': result.get('confidence'), 'questions': asked,
            'routing_top1_correct': bool(groups) and groups[0] == label['expected_resolver_group_id'],
            'routing_top3_correct': label['expected_resolver_group_id'] in groups[:3],
            'mandatory_human': label['human_required'],
            'mandatory_human_compliant': not label['human_required'] or result.get('recommended_action') == 'ESCALATE',
            'premature_proxy': bool(initial_diagnosis) and label.get('requires_questions', False),
            'resolution_ready_false': result.get('recommended_action') == 'RESOLVE' and not label['agent_resolvable'],
            'expected_agent_resolvable': label['agent_resolvable'],
            'scenario_type': label['scenario_type'], 'cluster_id': label.get('cluster_id'),
            'escalated': result.get('recommended_action') == 'ESCALATE'})
    except Exception as exc:
        results.append({'ticket_id': ticket['ticket_id'], 'language': ticket.get('language'),
            'diagnosis_correct': False, 'error': str(exc)})

n = len(results)
def rate(key, subset=results):
    return round(sum(bool(r.get(key)) for r in subset) / len(subset), 4) if subset else None
mandatory = [r for r in results if r.get('mandatory_human')]
ready = [r for r in results if r.get('recommended_action') == 'RESOLVE']
summary = {'tickets': n, 'diagnostic_accuracy': rate('diagnosis_correct'),
    'routing_recommendation_top1': rate('routing_top1_correct'), 'routing_recommendation_top3': rate('routing_top3_correct'),
    'mandatory_human_cases': len(mandatory), 'mandatory_human_compliance': rate('mandatory_human_compliant', mandatory),
    'resolution_ready_cases': len(ready), 'false_resolution_ready_rate': rate('resolution_ready_false', ready),
    'actual_resolution_rate': None, 'false_actual_resolution_rate': None,
    'potential_premature_diagnosis_proxy': rate('premature_proxy'),
    'errors': sum(bool(r.get('error')) for r in results),
    'by_language': {language: {'count': len(subset := [r for r in results if r['language'] == language]),
        'diagnostic_accuracy': rate('diagnosis_correct', subset)} for language in sorted({r['language'] for r in results})},
    'actions': dict(Counter(r.get('recommended_action', 'ERROR') for r in results)),
    'questions': sum(len(r.get('questions', [])) for r in results),
    'topic_matched_questions': sum(bool(q['topic']) for r in results for q in r.get('questions', []))}
output = {'package': args.package, 'evaluator_version': '2.0',
    'package_sha256': hashlib.sha256((ROOT / args.package).read_bytes()).hexdigest(), 'dataset_sha256': hashlib.sha256(tickets_path.read_bytes()).hexdigest(),
    'truth_sha256': hashlib.sha256(truth_path.read_bytes()).hexdigest(), 'summary': summary,
    'limitations': ['Independent authored data, but scripted-user topic matching is incomplete.',
        'Original-language answers only; no answer_en translation or labels passed to the agent.',
        'Raw ticket fixture fields are simulator inputs. No real backend writes or actual resolutions in this batch.',
        'Routing is a recommendation proxy; outage lifecycle belongs to collaborators and is not evaluated here.',
        'Premature diagnosis proxy flags initial diagnoses on cases marked requires_questions, not a clinical evidence adjudication.',
        'Dataset and oracle were inspected to implement evaluation; this is not an untouched post-development holdout.'], 'results': results}
(ROOT / args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary))

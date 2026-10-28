"""Run 15 controlled conversations through the relocated ZIP, no live writes."""
import hashlib
import argparse
import importlib.util
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from langchain_core.messages import AIMessage, HumanMessage

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--package', default='dist/isys-diagnostic-langgraph-v6.7.zip')
parser.add_argument('--report', default='docs/v67_dialogue_results.json')
args = parser.parse_args()
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
package = ROOT / args.package
temporary = tempfile.TemporaryDirectory(prefix='v67-dialogues-', dir=ROOT / 'dist')
entry = Path(temporary.name) / 'agent.py'
with zipfile.ZipFile(package) as archive:
    entry.write_bytes(archive.read('agent.py'))
spec = importlib.util.spec_from_file_location('v67_dialogue_agent', entry)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
spec.loader.exec_module(agent)
from test_v67_reasoning import DialogueBackend
from diagnostic_agent.answers import question_family

phrases = {
    'en': {'expired': 'The sign-in screen says password has expired.', 'locked': 'The screen says my account is locked.',
        'apps': 'Everything else works with my login.', 'peers': 'I asked two colleagues and they are connected without trouble.',
        'vpn': 'The VPN client reports a local configuration error.',
        'dns': 'Internal server names fail. Direct IP access works. External websites open normally.'},
    'ar': {'expired': 'الباسورد منتهي', 'locked': 'الحساب اتقفل', 'apps': 'باقي التطبيقات شغالة',
        'peers': 'زمايلي متصلين عادي', 'vpn': 'خطأ في الإعدادات',
        'dns': 'الأسماء الداخلية مش شغالة. الاي بي شغال. المواقع الخارجية بتفتح'},
    'franco_ar': {'expired': 'el password expired', 'locked': 'el account ma2fol', 'apps': 'el ba2i shaghal',
        'peers': 'zomalaey fe nafs el site metsleen 3adi', 'vpn': 'local configuration',
        'dns': 'asamy el servers mesh shaghal. el ip shaghal. el sites el khareg btefta7'},
}
results = []
for language, words in phrases.items():
    for scenario, code in [('password', 'PASSWORD_EXPIRED'), ('locked', 'ACCOUNT_LOCKED'),
            ('entitlement', 'MISSING_ENTITLEMENT'), ('vpn', 'VPN_CLIENT_ISSUE'), ('dns', 'DNS_FAILURE')]:
        backend = DialogueBackend()
        backend.ticket['language'] = language
        if scenario == 'password':
            backend.ticket.update(summary='Password expired', description='Sign-in screen says password expired')
            backend.account['password_expired'] = 'TRUE'
        elif scenario == 'locked':
            backend.ticket.update(summary='Account locked', description='Account is locked and sign-in fails')
            backend.account['locked'] = 'TRUE'
        elif scenario == 'entitlement':
            backend.ticket.update(summary='Portal access denied', description='Missing application role')
            backend.entitlement = {'entitled': 'FALSE', 'provisioning_state': 'ABSENT'}
        elif scenario == 'vpn':
            backend.ticket.update(summary='VPN does not connect', description='VPN client fails')
        else:
            backend.ticket.update(summary='Cannot resolve internal hostnames', description='Internal DNS failure')
        agent.DiagnosticBackendClient = lambda **kwargs: backend
        previous = None
        transcript = []
        text = 'Investigate INC-PW-READY'
        for index in range(7):
            messages = ([AIMessage(content=previous.content)] if previous else []) + [HumanMessage(content=text)]
            output = agent.create_agent({'configurable': {'credentials': {'isys_it_backend_api_key': 'synthetic-test-key'}}}).compile().invoke({'messages': messages})
            previous = output['messages'][-1]
            result = output['diagnostic_result']
            transcript.append({'user': text, 'reply': previous.content, 'result': result})
            assert not result['error'], result
            if result['recommended_action'] != 'ASK_MORE':
                break
            family = question_family(result['next_question'] or '')
            if scenario == 'password':
                text = words['expired']
            elif scenario == 'locked':
                text = words['locked']
            elif scenario == 'entitlement':
                text = words['apps']
            elif scenario == 'vpn':
                text = words['peers'] if family == 'vpn_peer' else words['vpn']
            else:
                text = words['dns']
        passed = result['diagnosis'] == code and result['recommended_action'] == ('RESOLVE' if scenario == 'password' else 'ROUTE')
        results.append({'scenario': scenario, 'language': language, 'passed': passed, 'transcript': transcript})
        print(json.dumps({'scenario': scenario, 'language': language, 'passed': passed}))
report = {'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(), 'mode': 'OFFLINE_SIMULATED_BACKEND',
    'passed': sum(r['passed'] for r in results), 'total': len(results), 'results': results}
(ROOT / args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
assert report['passed'] == report['total'], 'Inspect docs/v67_dialogue_results.json'

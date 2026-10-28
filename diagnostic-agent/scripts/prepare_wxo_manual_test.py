"""Prepare one fresh synthetic WXO test ticket; never invoke the agent.

Without --case this only lists cases. Creating a ticket uses the existing .env
backend connection. It does not alter account, entitlement or health fixtures.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = {}


def add(numbers, label, summary, description, person='USR-006', **extra):
    for number in numbers:
        CASES[str(number).zfill(2)] = {'label': label, 'summary': summary, 'description': description,
            'reported_by_id': person, 'affected_person_id': person, 'reported_priority': 3, 'language': 'en', **extra}


add([1, 2, 3, 4, 16, 28], 'Password workflow', 'Password expired',
    'The sign-in screen says my password expired and I cannot sign in.', 'USR-001')
add([5], 'Account lock', 'Account locked', 'The sign-in screen says my account is locked.', 'USR-002')
add([6], 'Application entitlement', 'Portal access denied', 'The Portal opens but I cannot use its menus.', 'USR-004',
    configuration_item_id='CI-PORTAL', location_id='LOC-E')
add([7, 8, 23], 'VPN scope', 'VPN client fails', 'The VPN client cannot connect.',
    configuration_item_id='CI-VPN', location_id='LOC-D')
add([9, 10], 'DNS comparison', 'Cannot resolve internal hostnames', 'Internal server names fail.',
    configuration_item_id='CI-DNS', location_id='LOC-B')
add([11], 'Vague intake to account lock', 'Unclear sign-in problem', 'Something is preventing my work.', 'USR-002')
add([12], 'Vague intake to application access', 'Unclear application problem', 'Something is preventing my work.',
    'USR-004', configuration_item_id='CI-PORTAL', location_id='LOC-E')
add([13], 'Wi-Fi pairing', 'Wi-Fi connection failure', 'My device cannot connect to the office Wi-Fi.',
    configuration_item_id='CI-WIFI', location_id='LOC-B')
add([14], 'Shared printer', 'Printer offline', 'The office printer is not reachable.')
add([15], 'Unknown symptoms', 'Unclear problem', 'Something is not working.')
add([17], 'Priority 1', 'Cannot access application', 'An application is not working.', reported_priority=1)
add([18], 'Security flag', 'Suspicious login', 'An unrecognized login was reported.', security_sensitive=True)
add([19], 'Privileged flag', 'Admin access required', 'A task requires privileged access.', privileged_access=True)
add([20], 'Late security disclosure', 'Unclear sign-in problem', 'Something is preventing my work.')
add([21], 'Arabic password', 'Password expired', 'The sign-in screen says my password expired.', 'USR-001', language='ar')
add([22], 'Franco-Arabic VPN', 'VPN client fails', 'The VPN client cannot connect.', language='franco_ar',
    configuration_item_id='CI-VPN', location_id='LOC-D')
add([24], 'Unobserved VPN health scope', 'VPN client fails', 'The VPN client cannot connect.',
    configuration_item_id='CI-VPN', location_id='LOC-C')
for number, entry in enumerate(json.loads((ROOT / 'docs/self_service_article_manifest.json').read_text(encoding='utf-8')), 31):
    add([number], entry['title'], entry['title'], entry['example_report'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', help='Case number, for example 01. Creates a fresh synthetic ticket.')
    args = parser.parse_args()
    if not args.case:
        print(json.dumps({k: v['label'] for k, v in CASES.items()}, indent=2))
        return
    number = args.case.zfill(2)
    if number not in CASES:
        parser.error('Choose a listed creation case. Cases 25–27 and 29–30 reuse a ticket or test the host; see the test pack.')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    sys.path.insert(0, str(ROOT / 'adk-project/agents'))
    from diagnostic_agent.backend_client import DiagnosticBackendClient
    payload = dict(CASES[number])
    label = payload.pop('label')
    payload['summary'] = '[WXO v6.7 case ' + number + '] ' + payload['summary']
    payload['action_id'] = 'wxo-test-' + uuid.uuid4().hex
    ticket = DiagnosticBackendClient().create_ticket(payload)
    result = {'case': number, 'label': label, 'ticket_id': ticket['ticket_id'],
        'prompt': 'Investigate ' + ticket['ticket_id'], 'status': ticket.get('status'), 'agent_run': False}
    target = ROOT / 'docs/wxo_v67_prepared_tickets.json'
    existing = json.loads(target.read_text(encoding='utf-8')) if target.exists() else []
    existing.append(result)
    target.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()

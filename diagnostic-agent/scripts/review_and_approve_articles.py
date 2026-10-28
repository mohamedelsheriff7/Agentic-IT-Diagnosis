"""Record the owner's delegated review approval; does not publish/import knowledge."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'adk-project/knowledge/reviewed'
PATH = DIRECTORY / 'diagnostic_articles.json'
rows = json.loads(PATH.read_text(encoding='utf-8'))
before = deepcopy(rows)
register_path = DIRECTORY / 'approval_register.json'
register = json.loads(register_path.read_text(encoding='utf-8'))
if register.get('backend_alignment', {}).get('mode') == 'EXACT_BACKEND_MIRROR':
    raise SystemExit('KB-001 is now backend-aligned. Do not reapply the historical bulk wording; use align_kb001_to_backend.py for authoritative refresh.')
history = register.get('approval_history', [])
if register.get('article_approvals') and not history:
    history.append({'decision': 'Earlier scoped KB-001 approval',
        'article_approvals': deepcopy(register['article_approvals'])})

EVIDENCE = {
 'KB-001': ['Recorded account check reports password_expired=TRUE, enabled=TRUE, locked=FALSE and mfa_locked=FALSE.',
     'User reports an explicit expiry message or a fresh sign-in failure consistent with expiry; alternatives and cached sessions are considered.',
     'Before resolution: the user completes the approved identity-verification/password-change flow and explicitly confirms the original sign-in problem is fixed.'],
 'KB-002': ['Recorded account check reports locked=TRUE; retain enabled and password-expired observations.',
     'An authorized IAM/security source verifies the lock reason before classifying it as ordinary lockout. The implemented account check does not expose that reason.',
     'Record the user account of failed attempts or stale clients as USER_RESPONSE evidence; do not treat it as independent verification of the lock reason.'],
 'KB-003': ['Record whether the password stage succeeds and the failure occurs at MFA, including the non-secret error and device-change history.',
     'Preserve actual account-check mfa_enrolled/mfa_locked results where available; UNKNOWN does not establish enrollment or lock state.',
     'Registration mismatch, push-delivery failure or device-specific faults need authorized IAM evidence; no MFA code is collected.'],
 'KB-004': ['Recorded entitlement check identifies the exact application and reports entitled=FALSE or provisioning_state=ABSENT.',
     'Record the access-denied/role error and whether fresh sign-in to other applications works; cached sessions alone do not establish healthy authentication.',
     'Approval/provisioning changes require the application owner; do not infer approval from a request or retrieval.'],
 'KB-005': ['Record the exact application-specific SSO/authentication error, timing and affected-user scope.',
     'Compare recorded account, entitlement and exact-CI service-health results; preserve UNKNOWN and conflicting observations.',
     'A specific SSO mapping/session root cause requires authorized application-log evidence; working cached sessions elsewhere do not rule out account issues.'],
 'KB-006': ['Record the affected device, failed task, error and whether the same task succeeds on another comparable device.',
     'Record shared-service status and peer scope. A local-device pattern does not establish a particular OS, driver or hardware fault.',
     'A component diagnosis requires authorized endpoint logs or measurements; the agent has no direct endpoint-health tool.'],
 'KB-007': ['Record the affected application/CI, location, onset window and reports from affected users.',
     'Preserve actual service-health observations and scoped recent-ticket/global-ticket search results when available.',
     'Shared scope triggers Supervisor outage screening. A confirmed outage requires reconciliation of conflicting observations; no threshold or monitor alone confirms or excludes it.'],
 'KB-008': ['Record VPN failure for multiple users at the same site and the time window, including non-secret errors and other network access.',
     'Preserve VPN CI/location service-health results and scoped recent-ticket/global-ticket results where available.',
     'A shared VPN problem is a screening hypothesis until authorized investigation reconciles the evidence; no global incident is created by the Diagnostic Agent.'],
 'KB-009': ['Record the reported suspicious behavior, message reference/time and whether a link, attachment or credential-entry action occurred; do not copy secrets or open content.',
     'Treat the report as suspected phishing requiring Security Operations review, not a verified malicious-message diagnosis.',
     'Only an authorized security analysis can establish maliciousness or a benign outcome.'],
 'KB-010': ['Record the requested elevated task, scope, duration and business justification without collecting credentials.',
     'Preserve actual approval references from authorized IAM/security sources. A chat request is not approval.',
     'The agent classifies and hands off the request; it neither grants privileges nor confirms that access was granted.'],
 'KB-011': ['Record the affected host/service CI, location, onset and affected-user/service scope.',
     'Preserve actual exact-CI service-health observations; identify which dependency is measured rather than assuming all are checked.',
     'A server/dependency root cause requires authorized infrastructure logs or measurements; shared observations first go to Supervisor screening.'],
 'KB-012': ['Record the affected service/device, symptom/error, onset, location and user scope, or explicitly mark each missing item.',
     'No root cause is established. Use INCONCLUSIVE with diagnosis_code=null while gathering evidence.',
     'Request human triage when useful questions/checks are exhausted; do not convert vague similarity or UNKNOWN tool results into a diagnosis.'],
 'KB-013': ['Record hostname access and direct-IP access to the same destination, plus whether external websites resolve/open.',
     'Name failure with successful direct-IP access supports a name-resolution pattern; preserve negative or contradictory observations and the affected scope.',
     'A resolver/record/cache root cause requires an authorized DNS lookup comparison. The agent has no implemented DNS lookup tool.'],
 'KB-014': ['Record whether a comparable device joins the same Wi-Fi at the same location and whether the affected device joins a different approved network.',
     'Record the connection error and affected-user/device scope. The device/network pairing pattern does not identify a faulty access point, adapter or profile.',
     'A component diagnosis requires authorized association/authentication logs or measurements; the agent has no direct Wi-Fi diagnostic tool.'],
 'KB-015': ['Record the low-space warning, affected endpoint/volume and whether the path is local or shared.',
     'Obtain measured free space/quota from an authorized user or endpoint-support source before declaring capacity exhaustion; the agent has no disk-metrics tool.',
     'Retain evidence of shared impact or malware/data-integrity concerns; do not infer that any particular file is disposable.'],
 'KB-016': ['Record the exact printer, affected-user scope and whether peers on the same network can reach/use it.',
     'Obtain actual power/status/queue observations from the user or authorized support; the agent has no printer-status or queue-management tool.',
     'Reachability symptoms alone do not confirm power loss, a spooler fault or a network root cause.'],
 'KB-017': ['Record the exact non-secret application error, failed action, timestamp and reproducible input characteristics.',
     'Compare whether colleagues can reproduce the same function failure and preserve actual service-health evidence.',
     'A defect/input/dependency diagnosis requires authorized application logs or safe reproduction evidence; similarity alone is insufficient.'],
 'KB-018': ['Record source-update time, destination-observed time, synthetic record references and whether all or only some records are delayed.',
     'A reported freshness mismatch supports a synchronization-delay pattern, not a confirmed queue or connection cause.',
     'Queue status, rejected records and last-success timestamps require authorized application-support evidence; no direct synchronization check is implemented.'],
 'KB-019': ['Record the security-alert reference/time or reported suspicious endpoint behavior without opening suspected files or collecting secrets.',
     'Treat unverified behavior as suspected compromise and stop routine troubleshooting.',
     'An authorized Security Operations investigation must distinguish malware, benign behavior and false positives.'],
 'KB-020': ['Record minimum necessary data category, sharing reference, time, intended recipient and reported access scope; do not copy sensitive contents.',
     'Preserve any authorized containment or access evidence without claiming an action occurred based only on a user request.',
     'Security/privacy owners determine whether exposure occurred, its scope and any required notification.'],
 'KB-021': ['Record the affected shared storage CI/path category, read versus write failure, onset and affected-user scope.',
     'Preserve actual service-health and authorized capacity/quota/permission observations; distinguish local disk exhaustion.',
     'Storage-backend, capacity and permission root causes require authorized infrastructure evidence; shared impact first goes to Supervisor screening.'],
 'KB-022': ['Record the exact warning type: expiry, untrusted chain or hostname mismatch, and whether multiple users see it.',
     'An expired-certificate root cause requires actual certificate validity dates compared with a verified clock from an authorized source.',
     'Shared expiry warnings support a symptom pattern only; the agent has no certificate-inspection tool and must not recommend bypassing validation.'],
 'KB-023': ['Recorded account check reports enabled=FALSE for the exact affected person; preserve locked and password-expired observations too.',
     'Record the disabled/deactivated message without assuming the lifecycle or security reason.',
     'Authorized IAM evidence must establish the reason and any reactivation approval.'],
 'KB-024': ['Record the supported service/platform/version and the task the user wants to learn, distinguishing a how-to request from an actual fault.',
     'Retrieve a concrete, separately approved platform-specific procedure before giving setup steps; this generic classification article is not that procedure.',
     'Task success cannot be inferred from delivering guidance. This article does not authorize resolve_ticket.'],
 'KB-025': ['Record the security-policy/suspicious-sign-in notice or authorized security-alert reference.',
     'An authorized IAM/security source must establish a security-policy lock reason. The ordinary account-status check reports state, not the policy reason.',
     'Retain uncertainty and route suspected compromise to Security Operations without attempting unlock.'],
 'KB-026': ['Record whether colleagues at the same site can connect now, whether ordinary internet access works and the exact local configuration versus credential error.',
     'Preserve actual VPN service-health results; UNKNOWN is missing evidence and a healthy monitor does not negate reported peer failures.',
     'Peer success plus a client error supports an individual symptom pattern; client/profile/credential root cause requires authorized logs. New shared impact returns to Supervisor screening.'],
}

PATCHES = {
 'KB-001': {'exclusion_criteria': ['Recorded password_expired=FALSE contradicts expiry. Disabled, locked or MFA-locked states block the self-service path and require investigation.',
     'Failure limited to one application is a clue, not a universal account/password exclusion: consider cached sessions and app-specific authentication.']},
 'KB-002': {'safe_checks': ['Use the implemented account check for enabled/locked/password-expired/MFA state with the exact affected-person ID. Obtain the security lock reason from authorized IAM/Security Operations; no implemented check exposes that reason. Do not attempt repeated sign-ins.']},
 'KB-007': {'exclusion_criteria': ['Peer success and an operational check may reduce the shared-outage hypothesis but do not exclude partial, intermittent or unmonitored faults.',
     'Different CI/location/time scope changes screening relevance; a low ticket count is not proof that no outage exists.']},
 'KB-008': {'exclusion_criteria': ['Only one device failing while peers connect favors an individual issue; preserve later shared-impact reports or contradictory health evidence.',
     'A low scoped ticket count or reports from different sites/times does not prove the VPN is healthy.']},
 'KB-023': {'exclusion_criteria': ['enabled=TRUE contradicts disabled state. Locked and expired-password observations can coexist with disablement and must not silently exclude enabled=FALSE.']},
 'KB-025': {'safe_checks': ['Read ordinary account state where available and preserve security-alert references. Ask an authorized IAM/security source to verify the lock reason; do not invent a policy-reason tool, unlock an account or bypass controls.']},
 'KB-024': {'agent_resolvable': False},
}

BOUNDARY = ('Execution boundary: the agent may use only implemented account-status, entitlement and exact-CI/location service-health checks with valid IDs. '
    'Other checks named in this article require an authorized human or a separately implemented tool. '
    'Record user observations as USER_RESPONSE, never TOOL_CHECK; UNKNOWN is unavailable evidence, not a healthy result.')

review = []
for article in rows:
    identifier = article['article_id']
    original = next(a for a in before if a['article_id'] == identifier)
    article['required_evidence'] = EVIDENCE[identifier]
    article.update(PATCHES.get(identifier, {}))
    if identifier == 'KB-001' and not any(c['field'] == 'mfa_locked' for c in article['resolution_conditions']):
        article['resolution_conditions'].append({'tool': 'check_account_status', 'field': 'mfa_locked', 'equals': 'FALSE'})
    if identifier in {'KB-007', 'KB-008'}:
        article['resolution_steps'][1]['instruction'] = ('Return impact evidence to the Supervisor for outage screening. '
            'Only an authorized human using an activated, approved policy may decide global-incident creation/linking and notification; '
            'the Diagnostic Agent does not perform or claim those actions.')
    if identifier == 'KB-015':
        article['resolution_steps'][0]['instruction'] = ('Review storage usage. An authorized user may choose an approved temporary-file cleanup procedure; '
            'do not delete business data or assume Downloads files are disposable. Stop if ownership or retention requirements are unclear.')
    if identifier == 'KB-019':
        article['safe_checks'] = ['Record the alert reference/time and report to Security Operations. Only authorized incident responders decide isolation or cleanup; the Diagnostic Agent performs neither.']
    if identifier == 'KB-012':
        article['safe_checks'] = ['Collect service/CI, location and affected-user scope, then return to the Supervisor for renewed outage screening. Never issue a broad health check with guessed identifiers.']
    if BOUNDARY not in article['safe_checks']:
        article['safe_checks'].append(BOUNDARY)
    article['approved'] = True
    if {k: v for k, v in original.items() if k not in {'version', 'approved'}} != {
        k: v for k, v in article.items() if k not in {'version', 'approved'}}:
        article['version'] = original['version'] + 1
    sha = hashlib.sha256(json.dumps(article, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    changed = [k for k in article if original.get(k) != article[k]]
    review.append({'article_id': identifier, 'diagnosis_code': article['diagnosis_code'],
        'version': article['version'], 'decision': 'APPROVED',
        'scope': 'Diagnostic questions, evidence assessment and human handoff in the synthetic prototype; '
            + ('guided self-service resolution remains conditional on runtime/backend alignment and every recorded prerequisite.'
               if article['agent_resolvable'] else 'no agent resolution authorized.'),
        'agent_resolvable': article['agent_resolvable'], 'changed_fields': changed,
        'approved_on': '2026-10-25', 'approved_by': 'Project owner / requesting user; review and selection delegated to Codex',
        'authorization': 'check all and approve if they are ok', 'article_sha256': sha,
        'deployment_status': 'NOT_DEPLOYED'})

assert len(rows) == len({a['article_id'] for a in rows}) == 26
taxonomy = {a['diagnosis_code'] for a in json.loads((DIRECTORY.parent / 'taxonomy.json').read_text(encoding='utf-8'))}
assert all(a['diagnosis_code'] in taxonomy for a in rows)
assert [a['article_id'] for a in rows if a['agent_resolvable']] == ['KB-001']
assert all(a['resolution_conditions'] and not any(s['level'] == 'SPECIALIST' for s in a['resolution_steps'])
           for a in rows if a['agent_resolvable'])

PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
register.update(status='ARTICLES_APPROVED_POLICY_PENDING', articles_approved=True, policy_approved=False,
    approved_on='2026-10-25', approved_article_ids=[a['article_id'] for a in rows], pending_article_ids=[],
    agent_resolution_candidate_ids=['KB-001'], article_approvals=review, approval_history=history,
    note='All 26 reviewed version-3 articles approved after content corrections for scoped synthetic diagnostic guidance. '
        'Only KB-001 is an agent-resolution candidate; resolution prerequisites, human restrictions, backend alignment and deployment remain separate. '
        'Escalation policy activation is not approved by this article review.')
register_path.write_text(json.dumps(register, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(ROOT / 'docs/article_review_2026-10-25.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'reviewed': len(rows), 'approved': len(rows), 'agent_resolution_candidates': ['KB-001'],
    'policy_approved': False, 'deployed': False}))

"""Human replies and backend-backed conversation checkpoints, without an LLM."""
import hashlib
import json
import re
import uuid
import zlib
from .backend_client import BackendRequestError

RECEIPT = re.compile(r'Ticket:\s*([A-Za-z0-9_-]{1,100})\s*·\s*Ref:\s*(CHK-[a-f0-9]{16})')
CHECKPOINT_KIND = 'ISYS_CONVERSATION_CHECKPOINT_V1'

def save_checkpoint(client, ticket_id, session, result):
    """Use existing audited NOTE storage; no backend schema/deployment change."""
    document = json.dumps({'session': session, 'result': result}, ensure_ascii=False).encode('utf-8')
    compressed = zlib.compress(document)
    if len(document) > 2_000_000 or len(compressed) > 256_000:
        raise BackendRequestError('Conversation checkpoint exceeded the prototype storage limit.')
    encoded = compressed.hex()
    parts = [encoded[i:i+8000] for i in range(0, len(encoded), 8000)]
    reference = 'CHK-' + uuid.uuid4().hex[:16]
    digest = hashlib.sha256(compressed).hexdigest()
    for index, part in enumerate(parts):
        client.add_worklog_entry(ticket_id, {
            'action_id': f'{reference}-{index}', 'entry_type': 'NOTE',
            'summary': f'[DiagnosticAgent] Conversation checkpoint {reference}, part {index+1}/{len(parts)}.',
            'rationale': json.dumps({'kind': CHECKPOINT_KIND, 'reference': reference,
                'part': index, 'total': len(parts), 'sha256': digest, 'data_hex': part}),
        })
    return reference

def load_checkpoint(client, ticket_id, reference, *, record=None):
    record = client.get_ticket_details(ticket_id) if record is None else record
    parts = {}
    for log in record.get('worklogs', []):
        if log.get('entry_type') != 'NOTE':
            continue
        try:
            part = json.loads(log.get('rationale', ''))
        except (ValueError, TypeError):
            continue
        if isinstance(part, dict) and part.get('kind') == CHECKPOINT_KIND and part.get('reference') == reference:
            index = part.get('part')
            if isinstance(index, int) and 0 <= index < 64:
                parts[index] = part
    try:
        first = parts[0]
        total = first['total']
        if not isinstance(total, int) or not 1 <= total <= 64 or set(parts) != set(range(total)):
            raise ValueError('Incomplete checkpoint')
        if any(p['total'] != total or p['sha256'] != first['sha256'] for p in parts.values()):
            raise ValueError('Inconsistent checkpoint')
        compressed = bytes.fromhex(''.join(parts[i]['data_hex'] for i in range(total)))
        if len(compressed) > 256_000 or hashlib.sha256(compressed).hexdigest() != first['sha256']:
            raise ValueError('Invalid checkpoint checksum')
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, 2_000_001)
        if len(raw) > 2_000_000 or not inflater.eof or inflater.unused_data:
            raise ValueError('Invalid checkpoint data')
        document = json.loads(raw)
        session = document['session']
        if session.get('ticket_id') != ticket_id or session['snapshot']['ticket']['ticket_id'] != ticket_id:
            raise ValueError('Checkpoint belongs to a different ticket')
        session['checkpoint_ref'] = reference
        return document
    except (KeyError, ValueError, TypeError, zlib.error) as exc:
        raise BackendRequestError('The saved conversation could not be restored. Please resend the ticket ID to restart.') from None


def latest_checkpoint(client, ticket_id):
    """Resume the checkpoint matching the backend's latest recorded result.

    A new preview/import must not discard answers already saved on this ticket.
    Worklog order is irrelevant (the synthetic backend can freeze timestamps).
    """
    if not callable(getattr(client, 'get_ticket_details', None)):
        return None
    record = client.get_ticket_details(ticket_id)
    if record.get('status') in {'RESOLVED', 'CLOSED'}:
        return None
    latest_id = (record.get('latest_diagnostic_result') or {}).get('diagnostic_result_id')
    if not latest_id:
        return None
    references = set()
    for log in record.get('worklogs', []):
        if log.get('entry_type') != 'NOTE' or not log.get('summary', '').startswith('[DiagnosticAgent] Conversation checkpoint '):
            continue
        try:
            part = json.loads(log.get('rationale', ''))
        except (ValueError, TypeError):
            continue
        if (isinstance(part, dict) and part.get('kind') == CHECKPOINT_KIND and part.get('part') == 0
                and re.fullmatch(r'CHK-[a-f0-9]{16}', str(part.get('reference', '')))):
            references.add(part['reference'])
    for reference in sorted(references):
        try:
            document = load_checkpoint(client, ticket_id, reference, record=record)
        except BackendRequestError:
            continue
        if document['result'].get('diagnostic_result_id') == latest_id:
            return document
    return None

QUESTIONS_AR = {
    'Which specific application or service is affected?': 'ما اسم التطبيق أو الخدمة المحددة المتأثرة؟',
    'Can you access other corporate applications with the same account?': 'هل تستطيع الدخول إلى تطبيقات الشركة الأخرى باستخدام الحساب نفسه؟',
    'Can colleagues at the same site connect to VPN right now?': 'هل يستطيع زملاؤك في الموقع نفسه الاتصال بالـ VPN الآن؟',
    'Does the VPN client show a local configuration or credential error?': 'هل يعرض برنامج الـ VPN خطأ في الإعدادات أو بيانات الدخول؟',
    'What exact error message do you see, and when did the problem start?': 'ما نص رسالة الخطأ التي تظهر، ومتى بدأت المشكلة؟',
    'Does the sign-in screen explicitly say the password has expired?': 'هل تذكر شاشة تسجيل الدخول صراحةً أن صلاحية كلمة المرور انتهت؟',
}

def render_reply(result, session, language='en'):
    """Describe only observed facts and actions that actually succeeded."""
    arabic = language == 'ar'
    ticket_id = result.get('ticket_id') or session.get('ticket_id')
    snapshot = session.get('snapshot') or {}
    action = result.get('recommended_action')
    if result.get('checkpoint_error'):
        text = 'تعذر حفظ المحادثة للمتابعة. أعد إرسال رقم التذكرة للمحاولة مرة أخرى.' if arabic else 'I couldn’t save the conversation for the next step. Please resend the ticket ID to retry.'
    elif result.get('error'):
        if result.get('missing_configuration'):
            text = 'لا أستطيع الوصول إلى نظام التذاكر بعد. يحتاج المشغّل إلى مراجعة اتصال النظام.' if arabic else 'I can’t access the ticket system yet. An operator needs to check the backend connection.'
        elif result.get('backend_status') == 404:
            text = 'لم أتمكن من العثور على التذكرة. تأكد من رقمها.' if arabic else 'I couldn’t retrieve that ticket. Please check the ticket ID.'
        else:
            text = 'تعذر إكمال هذه الخطوة. أعد إرسال رقم التذكرة للمحاولة مرة أخرى.' if arabic else 'I couldn’t complete that step. Please resend the ticket ID to retry.'
    elif result.get('outcome') == 'ALREADY_CLOSED':
        text = 'هذه التذكرة محلولة أو مغلقة بالفعل.' if arabic else 'This ticket is already resolved or closed.'
    elif result.get('outcome') == 'RESOLVED':
        text = 'أكد نظام التذاكر تسجيل حل المشكلة.' if arabic else 'The ticket system confirmed that the issue is resolved.'
    elif snapshot.get('ticket', {}).get('metadata', {}).get('pending_correction_review'):
        text = ('سجلت تصحيحك للمراجعة. قد يغيّر الاستنتاج السابق؛ يجب أن يراجع المشرف الأدلة المصححة قبل أي إجراء آخر. التذكرة ما زالت مفتوحة.'
            if arabic else 'Your correction is recorded for Supervisor review. It may change the earlier conclusion; '
            'the Supervisor must review the corrected evidence before further action. Your ticket remains open.')
    elif result.get('handoff_status'):
        text = 'الخطوة المسجلة هي مراجعة المشرف أو فريق الدعم. لا توجد إجابة تشخيصية أخرى مطلوبة الآن.' if arabic else 'The recorded next step is Supervisor or support review. No further diagnostic answer is needed right now.'
    elif action == 'ASK_MORE':
        question = result.get('next_question')
        if not question:
            text = 'ما رقم التذكرة التي تريد فحصها؟' if arabic else 'What ticket would you like me to investigate?'
        else:
            account = next((e.get('value') for e in snapshot.get('evidence', [])
                if isinstance(e.get('value'), dict) and e['value'].get('password_expired') == 'TRUE'), None)
            lead = ('فحص الحساب يشير إلى انتهاء صلاحية كلمة المرور. أحتاج إلى معلومة أخرى لتأكيد سبب المشكلة.\n\n'
                if arabic else 'The account check shows an expired password. I need one more detail to confirm the issue.\n\n') if account else ''
            clarification = snapshot.get('ticket', {}).get('metadata', {}).get('clarification_question')
            if clarification == question:
                lead = 'للتوضيح، أحتاج إلى معرفة أي خيار تقصد.\n\n' if arabic else 'To clarify, which option describes what you observed?\n\n'
            text = lead + (QUESTIONS_AR.get(question, question) if arabic else question)
    elif action == 'ROUTE':
        code = result.get('diagnosis_code')
        name = 'انتهاء صلاحية كلمة المرور' if arabic and code == 'PASSWORD_EXPIRED' else (
            'an expired password' if code == 'PASSWORD_EXPIRED' else (code or 'the issue').replace('_', ' ').lower())
        if arabic:
            text = f'الأدلة تشير إلى {name}. أوصي بمراجعة فريق الدعم المختص. التذكرة ما زالت مفتوحة.'
        else:
            group = 'the IAM team' if code in {'PASSWORD_EXPIRED', 'ACCOUNT_LOCKED', 'MISSING_ENTITLEMENT', 'ACCOUNT_DISABLED'} else 'the appropriate support team'
            text = f'The evidence points to {name}. I recommend a review by {group}. Your ticket remains open.'
            findings = result.get('diagnostic_findings', {})
            label = name
            if findings.get('leading_hypothesis'):
                label = findings['leading_hypothesis']['description']
                group = findings.get('suggested_support_team', group)
                text = f'The evidence supports {label}. I recommend review by {group}. Your ticket remains open.'
            if snapshot.get('ticket', {}).get('metadata', {}).get('diagnosis_basis') == 'REPORTED_DIAGNOSTIC_PATTERN':
                observed = ' '.join(o['description'] for o in findings.get('observations', [])[:3])
                text = (f'You reported: {observed}\n\nThe reported observations support {label}. '
                    'This identifies the problem pattern; the underlying faulty component remains unverified. '
                    f'I recommend review by {group}. Your ticket remains open.')
    elif action == 'ESCALATE' and (result.get('diagnostic_blocker') or {}).get('kind') == 'ACCOUNT_VERIFICATION_UNAVAILABLE':
        text = ('لم يتمكن فحص الحساب من التحقق من حالة الحساب المطلوبة. سجلت ملاحظاتك، لكن تكرار التأكيد لا يعوض الفحص المستقل. '
                'يلزم تحقيق بشري؛ لم يتأكد تشخيص أو انقطاع مشترك، ولم يتم تغيير الحساب.' if arabic else
                'The account check could not verify the required account state. Your reported observations are recorded, '
                'but repeated confirmations cannot replace that independent check. Human investigation is required; '
                'no diagnosis or shared outage is confirmed and no account change was made.')
    elif action == 'ESCALATE':
        findings = result.get('diagnostic_findings', {})
        codes = {c.get('diagnosis_id') if isinstance(c, dict) else c
            for c in result.get('remaining_candidates', [])}
        # Also recognize older saved results whose candidate list omitted the
        # shared hypothesis despite a persisted peer-failure observation.
        peer_failure = any(entry.get('facts', {}).get('peer_vpn_connection') in {'FAILS', 'CONFLICTING'}
            for entry in snapshot.get('ticket', {}).get('metadata', {}).get('interpreted_answers', {}).values())
        shared = bool(codes & {'VPN_OUTAGE', 'APP_OUTAGE', 'APPLICATION_FAILURE', 'SERVER_FAILURE', 'STORAGE_FAILURE'}
            or result.get('outage_detection') or peer_failure)
        if shared:
            observations = ' '.join(o['description'] for o in findings.get('observations', [])[:4])
            text = ('قد تشير الملاحظات إلى مشكلة في خدمة مشتركة، لكن لم يتأكد وجود انقطاع. '
                'أوصي بأن يجري المشرف فحصًا لاحتمال الانقطاع للخدمة والموقع والتذاكر المرتبطة قبل متابعة استكشاف مشكلة جهاز فردي. '
                'التذكرة ما زالت مفتوحة.' if arabic else
                'These observations suggest a possible shared-service issue. An outage is not confirmed. '
                'I recommend Supervisor outage screening for this service, location, and related tickets '
                'before individual troubleshooting. Your ticket remains open.')
            if observations:
                text = ('سجلت الملاحظات التي ذكرتها: ' if arabic else 'You reported: ') + observations + '\n\n' + text
        elif findings.get('observations') and findings.get('leading_hypothesis') and not result.get('human_review', {}).get('review_id'):
            observations = ' '.join(o['description'] for o in findings['observations'][:4])
            hypothesis = findings['leading_hypothesis']
            inference = (f"This suggests {hypothesis['description']}, but the cause is not confirmed. "
                if hypothesis.get('supporting_evidence_ids') and not hypothesis.get('contradicting_evidence_ids')
                else 'These observations help narrow the scope, but the cause is not confirmed. ')
            gaps = ' '.join(findings.get('verification_gaps', []))
            group = findings.get('suggested_support_team', 'support')
            text = (f'You reported: {observations}\n\n{inference}{gaps} '
                f'I recommend review by {group}. Your ticket remains open.')
            if arabic:
                text = f'سجلت الملاحظات التي ذكرتها: {observations}\n\nالسبب لم يتأكد بعد. {gaps} أوصي بمراجعة فريق الدعم المختص. التذكرة ما زالت مفتوحة.'
        elif result.get('evidence_conflicts'):
            text = ('إجابتك تشير إلى مشكلة مشتركة، لكن فحص الخدمة يعطي نتيجة مختلفة. لم تتأكد حالة انقطاع عامة. أوصي بمراجعة المشرف لهذه الأدلة ونتائج فحص التذاكر المرتبطة. التذكرة ما زالت مفتوحة.'
                if arabic else 'Your answer suggests a shared problem, but the service check gives conflicting information. An outage is not confirmed. I recommend that the Supervisor reviews these findings and the related-ticket checks. Your ticket remains open.')
        elif result.get('human_review', {}).get('review_id'):
            text = 'طلبت مراجعة بشرية لأن هذه الحالة تتطلب تدخل فريق الدعم.' if arabic else 'I’ve requested a human review because this case requires support intervention.'
        elif {c.get('diagnosis_id') if isinstance(c, dict) else c for c in result.get('remaining_candidates', [])} & {'UNKNOWN_ISSUE', 'UNKNOWN_CAUSE'}:
            text = 'I still don’t have an identified application/device and a usable symptom or error. I recommend a support specialist helps collect those details before a diagnosis is made.'
        else:
            text = 'المعلومات المتاحة لا تكفي لتشخيص موثوق. أوصي بمراجعة مختص دعم.' if arabic else 'The available information isn’t enough for a reliable diagnosis. I recommend a support specialist reviews the case.'
    elif action == 'RESOLVE':
        progress = result.get('resolution_progress') or snapshot.get('ticket', {}).get('metadata', {}).get('resolution_progress', {})
        question = result.get('next_question')
        if progress.get('stage') == 'WAIT_SUCCESS':
            text = ('تم تسجيل اكتمال الخطوة. هل حُلّت مشكلة تسجيل الدخول الأصلية الآن؟ أكد بنعم أو لا.' if arabic
                else 'The approved step is recorded as completed. Does the original sign-in problem now work correctly? Please explicitly confirm yes or no.')
        elif progress.get('stage') == 'WAIT_STEP' and progress.get('steps'):
            from .resolution_guidance import step_question
            text = step_question(progress, 'ar' if arabic else 'en')
        else:
            text = question or 'An approved fix requires explicit completed steps and user confirmation before resolution.'
    else:
        text = 'تمت مراجعة المعلومات المتاحة لهذه التذكرة.' if arabic else 'I’ve reviewed the available information for this ticket.'
    if not result.get('error') and result.get('outcome') not in {'ALREADY_CLOSED', 'RESOLVED'}:
        gaps = []
        labels = {'check_account_status': 'account check', 'check_service_health': 'service-health check',
                  'check_application_entitlement': 'application-access check'}
        for check in result.get('checks', []):
            values = check.get('result', {})
            if isinstance(values, dict) and any(value == 'UNKNOWN' for value in values.values()):
                gaps.append(labels.get(check.get('tool'), 'diagnostic check') + ' returned UNKNOWN')
        for check in result.get('check_errors', []):
            gaps.append(labels.get(check.get('tool'), 'diagnostic check') + ' was unavailable')
        if gaps:
            lead = ('بعض نتائج الفحص غير معروفة أو غير متاحة؛ لا يمكن اعتبار ذلك دليلاً على سلامة الخدمة. '
                if arabic else 'The ' + '; the '.join(dict.fromkeys(gaps))
                + '. This is missing evidence, not confirmation that the account or service is healthy. ')
            text = lead + '\n\n' + text
    reference = session.get('checkpoint_ref')
    if ticket_id and reference:
        text += f'\n\nTicket: {ticket_id} · Ref: {reference}'
    elif ticket_id:
        text += f'\n\nTicket: {ticket_id}'
    return text

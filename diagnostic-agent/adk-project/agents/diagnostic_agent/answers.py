"""Conservative interpretation of observations for implemented question families.

These are reported facts, never tool results or instructions to execute actions.
Uncertainty, conflicting statements, and ambiguous either/or answers stay unknown.
"""
import re


def canonical_question(question):
    """Normalize only reviewed equivalent wording; never translate arbitrary KB text."""
    q = ' '.join(question.lower().replace('‑', '-').replace('‐', '-').split()).rstrip('?.؟')
    aliases = {
        'ما هو التطبيق الذي لا يعمل': 'Which specific application or service is affected?',
        'which application or device were you using when you noticed the problem': 'Which specific application or service is affected?',
        'ما هي رسالة الخطأ ومتى بدأت المشكلة': 'What exact error message do you see, and when did the problem start?',
        'ما هي رسالة الخطأ': 'What exact error message do you see, and when did the problem start?',
        'what exact error appears': 'What exact error message do you see, and when did the problem start?',
        'does the error explicitly say your password expired': 'Does the sign-in screen explicitly say the password has expired?',
        'does the sign-in error explicitly say the password has expired': 'Does the sign-in screen explicitly say the password has expired?',
        'do other applications using the same identity also reject sign-in': 'Can you access other corporate applications with the same account?',
        'do other applications accept the same identity': 'Can you access other corporate applications with the same account?',
    }
    return aliases.get(q, question)


def question_family(question):
    q = canonical_question(question).lower().replace('reached/seen', 'reached')
    rules = (
        ('other_apps', 'access other corporate applications'),
        ('other_apps', 'other corporate applications accept the same account'),
        ('account_message', 'sign-in screen explicitly say'),
        ('account_message', 'sign-in message explicitly say'),
        ('account_message', 'error message on the sign-in screen explicitly say'),
        ('application_scope', 'which specific application or service'),
        ('error_detail', 'what exact error message'),
        ('sign_in_detail', 'what exact sign-in message'),
        ('lock_message', 'screen currently report that the account is locked'),
        ('security_notice', 'security alert or suspicious-activity notice'),
        ('vpn_local', 'vpn client show a local configuration'),
        ('vpn_peer', 'colleagues at the same site connect to vpn'),
        ('dns_hosts', 'internal hostnames fail'), ('dns_external', 'external websites resolve normally'),
        ('wifi_peer', 'another device connect to the same wi-fi'),
        ('wifi_alternate', 'device connect to a different approved network'),
        ('printer_scope', 'one user affected or everyone using the same printer'),
        ('printer_peer', 'printer be reached by other users'),
        ('sync_scope', 'all records delayed or only specific records'),
        ('sync_destination', 'source system showing the updated data'),
        ('certificate_type', 'browser warning show an expired certificate'),
        ('certificate_scope', 'multiple users seeing the same certificate warning'),
    )
    return next((name for name, fragment in rules if fragment in q), None)


def uncertain(answer):
    return bool(re.search(r"\b(?:not sure|unsure|maybe|sometimes|possibly|might|perhaps|"
        r"don['’]?t know|do not know|cannot tell|can['’]?t tell|yes and no|m[ea]?sh 3aref|msh 3aref|momken)\b|مش عارف|لا أعرف|مش متأكد|مش متاكد|ربما", answer.lower()))


def explicit_observations(answer):
    """Extract named reported symptoms, including facts volunteered outside a question.

    These rules neither translate arbitrary text nor create tool evidence.
    Negated, hypothetical and instruction-bearing claims are not confirmations.
    """
    text = ' '.join(answer.lower().replace('’', "'").split())
    if uncertain(text) or re.search(r'[?؟]|\b(ignore|pretend|assume|override|say that|actually|correction|if|would)\b|تجاهل|افترض', text):
        return {}
    facts = {}
    # Names are meaningful only with an explicit observed state, not a keyword.
    for value, pattern in (
        ('EXPIRED', r'(?:password (?:has )?expired|password is expired|expired password|انتهت صلاحية كلمة المرور|كلمة المرور انتهت|الباسورد (?:منتهي|انتهى)|(?:el )?password (?:expired|enteha)|el basword enteha)'),
        ('LOCKED', r'(?:account (?:is )?locked|account was locked|الحساب (?:مقفل|اتقفل)|تم قفل الحساب|el (?:account|7esab) (?:et2afal|ma2fol))'),
        ('DISABLED', r'(?:account (?:is )?(?:disabled|deactivated)|الحساب (?:معطل|متوقف)|el account disabled)'),
    ):
        if re.search(pattern, text) and not re.search(r"(?:not|isn't|is not|never|مش|ليس).{0,20}(?:expired|locked|disabled|منتهي|مقفل|معطل)", text):
            facts.setdefault('account_message', value)
            if facts['account_message'] != value:
                facts['account_message'] = 'CONFLICTING'
    if re.search(r"(?:cannot|can't|will not|won't).{0,20}(?:get past|pass).{0,15}(?:sign.in|login)|مش قادر (?:اعدي|أعدي) شاشة الدخول", text):
        facts['account_signin_blocked'] = 'TRUE'
    if re.search(r'\b(?:access denied|no permission|missing role|missing entitlement|menus? (?:is |are )?empty|every menu is empty)\b|لا (?:توجد|املك|أملك) صلاحية|مفيش صلاحية|mafeesh sala7eya', text) and not re.search(r'\bno (?:permission|access) (?:issues?|problems?)\b', text):
        facts['application_access_detail'] = 'ACCESS_DENIED'
    if re.search(r'\b(?:everything else|all other (?:applications|apps)|other corporate applications)\b.{0,40}\b(?:works?|opens?|accepts? (?:my|the|this) (?:login|account))\b', text):
        if not re.search(r"\b(?:not|don't|doesn't|do not|does not) work", text):
            facts['other_application_access'] = 'WORKS'
    if re.search(r'\b(?:cannot|can\x27t|unable to) (?:access|sign in to|log in to) (?:any |the )?(?:other|all) (?:corporate )?(?:applications|apps)\b', text):
        facts['other_application_access'] = 'FAILS'
    if re.search(r'\b(?:cached|already signed in|existing session)\b|جلسة قديمة|cached session', text):
        facts.pop('other_application_access', None)
    for field, subject in (
        ('hostname_access', r'(?:internal (?:hostnames?|server names?|names?)|server names?|الاسماء الداخلية|الأسماء الداخلية|asamy el servers)'),
        ('direct_ip_access', r'(?:direct ip(?: access)?|el ip|الاي بي|الآي بي)'),
        ('external_web_access', r'(?:external (?:websites?|sites?)|المواقع الخارجية|المواقع الخارجيه|el sites el khareg)')):
        found = set()
        for clause in re.split(r'[.;]|\bbut\b|\bwhile\b|لكن', text):
            match = re.search(subject + r'.{0,55}', clause)
            if not match:
                continue
            claim = match.group()
            if re.search(r"\b(?:not|do not|don't|does not|doesn't) fail\b", claim):
                continue
            if re.search(r"\b(?:fail\w*|cannot|can't|do not|don't|not work)\b|مش (?:شغال|بتفتح)|لا (?:تعمل|تفتح)|(?:mesh|msh) (?:shaghal|btefta7)", claim):
                found.add('FAILS')
            elif re.search(r'\b(?:works?|open(?:s)? normally|resolves? normally)\b|شغال|بتفتح|تعمل|shaghal|btefta7', claim):
                found.add('WORKS')
        if len(found) == 1:
            facts[field] = found.pop()
        elif found:
            facts[field] = 'CONFLICTING'
    return facts


def interpret_answer(question, answer):
    """Return narrow, question-scoped facts or None when interpretation is unsafe."""
    family = question_family(question)
    if uncertain(answer):
        return None
    text = ' '.join(answer.lower().replace('’', "'").replace('wi-fi', 'wifi').split())
    # Imperatives do not become observations, even when they contain a quoted fact.
    if re.search(r'\b(?:ignore|pretend|say that|tell me that|assume|override)\b', text):
        return None
    # An explicit revision within one answer needs clarification; selecting the
    # first matching clause can reverse the user's intended scope.
    if re.search(r'\b(?:actually|correction|on second thought|i was wrong)\b', text):
        return None
    if family == 'other_apps' and re.search(r'\b(?:cached|already signed in|existing session)\b', text):
        return None
    facts = explicit_observations(answer)

    def status(field, subject, positive, negative):
        found = set()
        # Bounded clauses prevent a predicate about a second subject leaking across.
        for clause in re.split(r'[.;\n]|\bbut\b|\bwhile\b', text):
            if re.search(r"\b(?:not|don\x27t|doesn\x27t|do not|does not) fail\b", clause):
                continue
            if re.search(subject + r'.{0,65}\b(?:' + negative + r')\b', clause):
                found.add('FAILS')
            elif re.search(subject + r'.{0,65}\b(?:' + positive + r')\b', clause):
                found.add('WORKS')
        if len(found) == 1:
            facts[field] = found.pop()

    if family == 'other_apps':
        status('other_application_access', r'\b(?:i|we|this account)\b',
            r'can access|can sign in|can log in', r'cannot access|can\x27t access|unable to access|cannot sign in|cannot log in')
        if re.search(r'باقي|التطبيقات|البرامج|el ba2i|ba2y|other apps', text):
            if re.search(r'مش (?:قادر|شغال)|لا (?:استطيع|أستطيع)|كلها (?:بترفض|مش)|(?:mesh|msh) (?:shaghal|ader)|ma2darsh', text):
                facts['other_application_access'] = 'FAILS'
            elif re.search(r'شغال|بتفتح|بدخل|shaghal|btefta7', text):
                facts['other_application_access'] = 'WORKS'
    elif family == 'vpn_peer':
        if re.search(r'\b(?:some|few).{0,50}\b(?:others|other colleagues)\b|بعض|ba3d|ناس.{0,40}ناس', text):
            return None
        if re.search(r'\b(?:no colleagues|none of (?:my|our|the) colleagues)\s+(?:cannot|can\x27t)', text):
            return None
        text = re.sub(r'\b(?:no (?:colleagues|other users)|none of (?:my|our|the) (?:colleagues|other users))\s+can connect\b',
            'colleagues cannot connect', text)
        status('peer_vpn_connection', r'\b(?:colleagues|others|other users)\b',
            r'can connect|connect successfully|connect fine|(?:are )?connected (?:fine|without trouble|normally)', r'cannot connect|can\x27t connect|unable to connect')
        peer = re.search(r'(?:زمل\S*|زمايل\S*|باقي الناس|zom\w*|zama\w*).{0,75}', text)
        if peer:
            clause = peer.group()
            if re.search(r'مش (?:قادر|متصل|متوصل)|لا يستطيع|(?:mesh|msh) (?:shaghal|metsl|metwas|byets)|ma2darosh', clause):
                facts['peer_vpn_connection'] = 'FAILS'
            elif re.search(r'متصل|متوصل|بيتصل|شغال|metsleen|metwasleen|shaghal|byetselo', clause):
                facts['peer_vpn_connection'] = 'WORKS'
    elif family == 'vpn_local':
        if re.fullmatch(r'(?:a )?local configuration(?: error)?[.!]?', text):
            facts['vpn_client_error'] = 'LOCAL_CONFIGURATION'
        elif re.fullmatch(r'(?:a )?(?:credential|authentication)(?: error)?[.!]?', text):
            facts['vpn_client_error'] = 'AUTHENTICATION'
        elif re.search(r'\b(?:client|vpn)\b.{0,50}\b(?:shows?|reports?)\b.{0,35}\b(?:configuration|credential|authentication) error\b', text):
            if re.search(r'\b(?:no|not|never|without)\b', text):
                return None
            config = bool(re.search(r'\blocal configuration error\b', text))
            auth = bool(re.search(r'\b(?:credential|authentication) error\b', text))
            facts['vpn_client_error'] = ('LOCAL_CONFIGURATION' if config and not auth
                else 'AUTHENTICATION' if auth and not config else 'REPORTED')
        if re.search(r'خطأ (?:في )?(?:الاعدادات|الإعدادات)|مشكلة (?:في )?(?:الاعدادات|الإعدادات)|moshkelet settings|local config(?:uration)? error', text):
            if not re.search(r'\b(?:no|not|without) local config|مفيش مشكلة', text):
                facts['vpn_client_error'] = 'LOCAL_CONFIGURATION'
    elif family and family.startswith('dns_'):
        status('hostname_access', r'\b(?:hostnames?|server names?|internal names?)\b',
            r'works?|resolves?|succeeds?', r'fails?|cannot resolve|can\x27t resolve|do not resolve|don\x27t resolve|not work')
        status('direct_ip_access', r'\b(?:direct )?ip(?: address)?(?: access)?\b',
            r'works?|succeeds?|accessible', r'fails?|not work|cannot connect|can\x27t connect|unreachable')
        status('external_web_access', r'\b(?:external|public) (?:websites?|sites?)\b',
            r'open(?:s)? normally|resolve(?:s)? normally|work(?:s)?|accessible',
            r'not (?:open|resolve|work)|fail(?:s)?|cannot (?:open|resolve)|can\x27t (?:open|resolve)')
        for field, subject in (('hostname_access', r'(?:الاسماء|الأسماء|اسامي السيرفرات|asamy el servers|internal names)'),
                               ('direct_ip_access', r'(?:الاي بي|الآي بي|direct ip|el ip)'),
                               ('external_web_access', r'(?:المواقع الخارجية|المواقع الخارجيه|external sites|el sites el khareg)')):
            clause = re.search(subject + r'.{0,50}', text)
            if clause:
                if re.search(r'مش (?:شغال|بتفتح)|لا (?:تعمل|تفتح)|(?:mesh|msh) (?:shaghal|btefta7)|بتفشل', clause.group()):
                    facts[field] = 'FAILS'
                elif re.search(r'شغال|بتفتح|تعمل|shaghal|btefta7', clause.group()):
                    facts[field] = 'WORKS'
    elif family == 'wifi_peer':
        status('peer_wifi_connection', r'\b(?:another|other|second) (?:device|devices)\b',
            r'connects?|can connect', r'cannot connect|can\x27t connect|not connect|fails?')
    elif family == 'wifi_alternate':
        if re.search(r'\b(?:different|another|alternate) (?:approved )?network\b', text):
            status('alternate_network_connection', r'\b(?:affected|this|the|my) device\b',
                r'connects?|can connect', r'cannot connect|can\x27t connect|not connect|fails?')
    elif family == 'printer_scope':
        shared = bool(re.search(r'\b(?:everyone|everybody|multiple users|several users|all users)\b', text))
        individual = bool(re.search(r'\b(?:only (?:me|one user|myself)|just me)\b', text))
        if shared != individual:
            facts['printer_scope'] = 'MULTIPLE_USERS' if shared else 'ONE_USER'
    elif family == 'printer_peer':
        status('peer_printer_access', r'\b(?:other users|colleagues|others|everyone)\b',
            r'can (?:reach|access|use)|able to (?:reach|access)|can print',
            r'cannot (?:reach|access|use)|can\x27t (?:reach|access|use)|unable to (?:reach|access)|cannot print')
    elif family == 'sync_scope':
        partial = bool(re.search(r'\b(?:only (?:some|specific|a few)|some) records\b', text))
        all_records = bool(re.search(r'\ball records\b', text))
        if partial != all_records:
            facts['sync_scope'] = 'SOME_RECORDS' if partial else 'ALL_RECORDS'
    elif family == 'sync_destination':
        if re.search(r'\bsource\b.{0,45}\b(?:updates|updated|new|correct)\b', text) and re.search(
                r'\bdestination\b.{0,45}\b(?:old|stale|not updated)\b', text):
            facts['destination_stale'] = 'TRUE'
    elif family == 'certificate_type':
        options = []
        if re.search(r'\b(?:certificate (?:has )?expired|expired certificate|certificate expired)\b', text):
            options.append('EXPIRED')
        if re.search(r'\bhostname mismatch\b', text):
            options.append('HOSTNAME_MISMATCH')
        if re.search(r'\buntrusted\b', text):
            options.append('UNTRUSTED')
        if len(options) == 1 and not re.search(r'\b(?:not expired|has not expired)\b', text):
            facts['certificate_warning'] = options[0]
    elif family == 'certificate_scope':
        if re.search(r'\b(?:multiple|several|other|all) users\b.{0,50}\b(?:same|warning|see)\b', text):
            facts['shared_certificate_warning'] = 'TRUE'

    # A bare boolean is useful for an actual yes/no question, not an either/or.
    normalized = text.strip(' .!?')
    yes = normalized in {'yes', 'y', 'yeah', 'correct', 'true', 'نعم', 'ايوه', 'أيوه', 'اه', 'aywa', 'ah'}
    no = normalized in {'no', 'n', 'nope', 'false', 'لا', 'لأ', 'la', 'la2'}
    boolean_fields = {
        'other_apps': 'other_application_access',
        'vpn_peer': 'peer_vpn_connection',
        'wifi_peer': 'peer_wifi_connection', 'wifi_alternate': 'alternate_network_connection',
        'printer_peer': 'peer_printer_access', 'dns_external': 'external_web_access',
    }
    negative_other_apps = 'other applications using the same identity also reject sign-in' in question.lower()
    prefix = re.match(r'^(yes|no)\b', text)
    expected_field = boolean_fields.get(family)
    if prefix and expected_field in facts:
        expected = 'WORKS' if (prefix.group(1) == 'yes') != negative_other_apps else 'FAILS'
        if facts[expected_field] != expected:
            return None
    if not facts and (yes or no) and family in boolean_fields:
        facts[boolean_fields[family]] = 'WORKS' if yes != negative_other_apps else 'FAILS'
    if not facts and yes and family == 'dns_hosts':
        facts.update(hostname_access='FAILS', direct_ip_access='WORKS')
    if not facts and (yes or no) and family == 'vpn_local':
        facts['vpn_client_error'] = 'REPORTED' if yes else 'NOT_REPORTED'
    if not facts and yes and family == 'sync_destination':
        facts['destination_stale'] = 'TRUE'
    if not facts and (yes or no) and family == 'certificate_scope':
        facts['shared_certificate_warning'] = 'TRUE' if yes else 'FALSE'
    if not facts and (yes or no) and family == 'account_message':
        value = 'DISABLED' if 'disabled' in question.lower() else 'EXPIRED'
        facts['account_message'] = value if yes else 'NOT_' + value
    if not facts and (yes or no) and family == 'lock_message':
        facts['account_message'] = 'LOCKED' if yes else 'NOT_LOCKED'
    if not facts and (yes or no) and family == 'security_notice':
        facts['security_notice'] = 'REPORTED' if yes else 'NOT_REPORTED'
    if not facts:
        return None
    if 'CONFLICTING' in facts.values():
        return None
    supports, contradicts = [], []
    message_codes = {'EXPIRED': 'PASSWORD_EXPIRED', 'LOCKED': 'ACCOUNT_LOCKED', 'DISABLED': 'ACCOUNT_DISABLED'}
    if facts.get('account_message') in message_codes:
        supports.append(message_codes[facts['account_message']])
    if facts.get('account_signin_blocked') == 'TRUE':
        supports.extend(['PASSWORD_EXPIRED', 'ACCOUNT_LOCKED', 'MFA_FAILURE'])
    if facts.get('application_access_detail') == 'ACCESS_DENIED':
        supports.extend(['MISSING_ENTITLEMENT', 'APP_AUTH_FAILURE'])
    if facts.get('other_application_access') == 'FAILS':
        supports.extend(['PASSWORD_EXPIRED', 'ACCOUNT_LOCKED', 'MFA_FAILURE'])
    elif facts.get('other_application_access') == 'WORKS':
        supports.extend(['MISSING_ENTITLEMENT', 'APP_AUTH_FAILURE'])
    if facts.get('vpn_client_error') in {'LOCAL_CONFIGURATION', 'AUTHENTICATION', 'REPORTED'}:
        supports.append('VPN_CLIENT_ISSUE')
    if facts.get('peer_vpn_connection') == 'WORKS':
        supports.append('VPN_CLIENT_ISSUE')
        contradicts.append('VPN_OUTAGE')
    elif facts.get('peer_vpn_connection') == 'FAILS':
        supports.append('VPN_OUTAGE')
        contradicts.append('VPN_CLIENT_ISSUE')
    if ((facts.get('hostname_access') == 'FAILS' and facts.get('direct_ip_access') == 'WORKS')
            or facts.get('external_web_access') == 'WORKS'):
        supports.append('DNS_FAILURE')
    if facts.get('alternate_network_connection') == 'WORKS' or facts.get('peer_wifi_connection') == 'FAILS':
        supports.append('WIFI_FAILURE')
    if facts.get('peer_printer_access') == 'FAILS':
        supports.append('PRINTER_OFFLINE')
    if 'sync_scope' in facts or facts.get('destination_stale') == 'TRUE':
        supports.append('SYNC_DELAY')
    if facts.get('certificate_warning') == 'EXPIRED':
        supports.append('CERT_EXPIRED')
    elif facts.get('certificate_warning') in {'HOSTNAME_MISMATCH', 'UNTRUSTED'}:
        contradicts.append('CERT_EXPIRED')
    return {'facts': facts, 'supports': supports, 'contradicts': contradicts}


def collected_facts(state):
    facts = {}
    entries = state.ticket.metadata.get('interpreted_answers', {})
    for entry in entries.values():
        for field, value in entry.get('facts', {}).items():
            previous = facts.get(field)
            facts[field] = value if previous in {None, value} else 'CONFLICTING'
    return facts


def question_answered(question, facts):
    family = question_family(question)
    if family == 'account_message':
        expected = 'DISABLED' if 'disabled' in question.lower() else 'EXPIRED'
        return facts.get('account_message') in {expected, 'NOT_' + expected}
    if family == 'lock_message':
        return facts.get('account_message') in {'LOCKED', 'NOT_LOCKED'}
    if family == 'sign_in_detail':
        return facts.get('account_message') in {'EXPIRED', 'LOCKED', 'DISABLED'}
    requirements = {
        'other_apps': ('other_application_access',), 'vpn_local': ('vpn_client_error',),
        'vpn_peer': ('peer_vpn_connection',),
        'dns_hosts': ('hostname_access', 'direct_ip_access'), 'dns_external': ('external_web_access',),
        'wifi_peer': ('peer_wifi_connection',), 'wifi_alternate': ('alternate_network_connection',),
        'printer_scope': ('printer_scope',), 'printer_peer': ('peer_printer_access',),
        'sync_scope': ('sync_scope',), 'sync_destination': ('destination_stale',),
        'certificate_type': ('certificate_warning',), 'certificate_scope': ('shared_certificate_warning',),
        'security_notice': ('security_notice',),
    }
    fields = requirements.get(question_family(question))
    return bool(fields) and all(facts.get(field) not in {None, 'CONFLICTING'} for field in fields)


FACT_TEXT = {
    ('peer_vpn_connection', 'WORKS'): 'Colleagues at the same site can connect to VPN.',
    ('peer_vpn_connection', 'FAILS'): 'Colleagues at the same site also cannot connect to VPN.',
    ('other_application_access', 'FAILS'): 'Other corporate applications are inaccessible with the same account.',
    ('other_application_access', 'WORKS'): 'Other corporate applications work with the same account.',
    ('vpn_client_error', 'LOCAL_CONFIGURATION'): 'The VPN client reports a local configuration error.',
    ('vpn_client_error', 'AUTHENTICATION'): 'The VPN client reports a credential/authentication error.',
    ('vpn_client_error', 'REPORTED'): 'The VPN client reports a configuration or credential error.',
    ('hostname_access', 'FAILS'): 'Internal server names fail.',
    ('hostname_access', 'WORKS'): 'Internal server names resolve successfully.',
    ('direct_ip_access', 'WORKS'): 'Direct IP access works.',
    ('direct_ip_access', 'FAILS'): 'Direct IP access fails.',
    ('external_web_access', 'WORKS'): 'External websites open normally.',
    ('external_web_access', 'FAILS'): 'External websites fail too.',
    ('peer_wifi_connection', 'WORKS'): 'Another device connects to the same Wi-Fi.',
    ('peer_wifi_connection', 'FAILS'): 'Other devices also cannot connect to that Wi-Fi.',
    ('alternate_network_connection', 'WORKS'): 'The affected device connects to a different approved network.',
    ('alternate_network_connection', 'FAILS'): 'The affected device also fails on a different approved network.',
    ('printer_scope', 'MULTIPLE_USERS'): 'Multiple users are affected at the same printer.',
    ('printer_scope', 'ONE_USER'): 'Only one user is affected at the printer.',
    ('peer_printer_access', 'FAILS'): 'Other users cannot reach the printer.',
    ('peer_printer_access', 'WORKS'): 'Other users can reach the printer.',
    ('sync_scope', 'SOME_RECORDS'): 'Only some records are delayed.',
    ('sync_scope', 'ALL_RECORDS'): 'All records are delayed.',
    ('destination_stale', 'TRUE'): 'The source has updates while the destination remains stale.',
    ('certificate_warning', 'EXPIRED'): 'The browser reports an expired certificate.',
    ('certificate_warning', 'HOSTNAME_MISMATCH'): 'The browser reports a hostname mismatch.',
    ('certificate_warning', 'UNTRUSTED'): 'The browser reports an untrusted certificate.',
    ('shared_certificate_warning', 'TRUE'): 'Multiple users report the same certificate warning.',
}


def diagnostic_findings(state):
    """Summarize observations and capability gaps with their real evidence IDs."""
    entries = state.ticket.metadata.get('interpreted_answers', {})
    observations = []
    seen = set()
    for evidence_id, entry in entries.items():
        for field, value in entry.get('facts', {}).items():
            description = FACT_TEXT.get((field, value))
            if description and description not in seen:
                observations.append({'description': description, 'evidence_id': evidence_id,
                    'source': 'USER_RESPONSE'})
                seen.add(description)
    codes = {c.diagnosis_id for c in state.candidates}
    specifications = (
        ('VPN_CLIENT_ISSUE', 'a VPN client configuration/authentication problem', 'Network Support', 'the client configuration and exact connection error'),
        ('DNS_FAILURE', 'a DNS/name-resolution problem', 'Network Support', 'a DNS lookup comparison for the affected hostname and configured resolver'),
        ('WIFI_FAILURE', 'a Wi-Fi connection problem', 'Network Support', 'Wi-Fi association logs and the affected network/profile configuration'),
        ('PRINTER_OFFLINE', 'a printer reachability problem', 'Endpoint Support', 'the printer power/network status and print-queue state'),
        ('SYNC_DELAY', 'a synchronization delay', 'Application Support', 'synchronization job logs and the affected record timestamps'),
        ('CERT_EXPIRED', 'an expired-certificate problem', 'Infrastructure Support', 'the certificate validity dates and service certificate chain'),
    )
    match = next((item for item in specifications if item[0] in codes), None)
    if not match:
        gaps = ['Identify the affected application/device and obtain an observable symptom or error.'] if codes & {'UNKNOWN_ISSUE', 'UNKNOWN_CAUSE'} else []
        return {'observations': observations, 'verification_gaps': gaps}
    code, hypothesis, group, required_check = match
    facts = collected_facts(state)
    if code == 'VPN_CLIENT_ISSUE':
        if facts.get('vpn_client_error') == 'LOCAL_CONFIGURATION':
            hypothesis = 'a VPN client local-configuration problem'
        elif facts.get('vpn_client_error') == 'AUTHENTICATION':
            hypothesis = 'a VPN client credential/authentication problem'
    if code == 'WIFI_FAILURE' and facts.get('peer_wifi_connection') == facts.get('alternate_network_connection') == 'WORKS':
        hypothesis = 'a Wi-Fi connection problem specific to this device/network pairing'
    supporting = [e.evidence_id for e in state.evidence if code in e.supports]
    conflicts = [e.evidence_id for e in state.evidence if code in e.contradicts]
    gap = f'A specialist needs to verify {required_check}; this agent has no implemented direct check for it.'
    return {'observations': observations, 'leading_hypothesis': {'diagnosis_code': code,
        'description': hypothesis, 'supporting_evidence_ids': supporting,
        'contradicting_evidence_ids': conflicts}, 'suggested_support_team': group,
        'verification_gaps': [gap] if not state.final_diagnosis else []}


def reported_pattern(state, code):
    """Recognize a symptom-level pattern; never authorize a repair or name an unverified component."""
    f = collected_facts(state)
    patterns = {
        'DNS_FAILURE': f.get('hostname_access') == 'FAILS' and f.get('direct_ip_access') == 'WORKS' and f.get('external_web_access') == 'WORKS',
        'WIFI_FAILURE': f.get('peer_wifi_connection') == 'WORKS' and f.get('alternate_network_connection') == 'WORKS',
        'PRINTER_OFFLINE': f.get('printer_scope') == 'MULTIPLE_USERS' and f.get('peer_printer_access') == 'FAILS',
        'VPN_CLIENT_ISSUE': f.get('peer_vpn_connection') == 'WORKS' and f.get('vpn_client_error') in {'LOCAL_CONFIGURATION', 'AUTHENTICATION', 'REPORTED'},
        'SYNC_DELAY': f.get('sync_scope') == 'SOME_RECORDS' and f.get('destination_stale') == 'TRUE',
        'CERT_EXPIRED': f.get('certificate_warning') == 'EXPIRED' and f.get('shared_certificate_warning') == 'TRUE',
    }
    return (state.ticket.metadata.get('diagnostic_review_mode') and patterns.get(code, False)
        and 'CONFLICTING' not in f.values()
        and any(m.get('diagnosis_code') == code for m in state.knowledge_matches))

"""A label-free scripted user: match requested observation topics, not diagnoses.

Only original-language answer text is returned. Repeated questions get the same
known answer rather than a fabricated 'unknown' because the fact was used once.
"""

def scripted_answer(question, available, used, question_family):
    family = question_family(question)
    q = question.lower()
    messages = ['exact_message', 'error_seen', 'exact_error', 'error_text', 'error_shown',
        'message_text', 'message_on_screen', 'any_error_message', 'banner_text', 'warning_text',
        'access_page_message', 'what_happens']
    groups = {
        'other_apps': ['other_corporate_applications', 'password_works', 'access_test'],
        'account_message': messages, 'lock_message': messages,
        'security_notice': ['security_alert_received', 'alert_details'],
        'vpn_peer': ['colleagues_affected', 'who_affected', 'same_for_colleague'],
        'vpn_local': ['client_message', 'connection_attempt'] + messages,
        'dns_hosts': ['dns_symptoms'],
        'dns_external': ['other_websites_load', 'other_sites_load', 'internet_ok'],
        'wifi_peer': ['other_devices', 'colleagues_affected'],
        'wifi_alternate': ['wifi_status', 'only_this_device'],
        'printer_scope': ['who_affected', 'colleagues_affected'],
        'printer_peer': ['same_for_colleague', 'printer_status', 'printer_panel'],
        'certificate_type': ['certificate_warning', 'warning_text'],
        'certificate_scope': ['colleagues_affected', 'same_for_colleague'],
        'sync_scope': ['colleague_sees_data', 'what_is_broken'],
        'sync_destination': ['time_to_appear', 'colleague_sees_data'],
    }
    topics = groups.get(family, [])
    if not topics:
        if 'other' in q and any(w in q for w in ('user', 'colleague', 'device')):
            topics = ['colleagues_affected', 'other_devices', 'same_for_colleague', 'only_this_device', 'others_slow']
        elif 'security' in q or 'suspicious' in q:
            topics = ['security_alert_received', 'alert_details', 'started_signin_myself']
        elif 'error' in q or 'message' in q or 'رسالة' in q:
            topics = messages + ['client_message', 'what_fails', 'what_is_broken']
        elif 'application' in q or 'device' in q or 'service' in q or 'تطبيق' in q:
            topics = ['what_application', 'which_application', 'device_or_app', 'what_is_broken']
        elif 'space' in q:
            topics = ['free_space', 'disk_space', 'big_folders']
        elif 'phone' in q or 'mfa' in q or 'verification' in q:
            topics = ['phone_changed', 'phone_type', 'old_phone_available', 'approved_any', 'started_signin_myself']
        elif 'password' in q and 'change' in q:
            topics = ['when_last_changed', 'recent_password_change', 'typed_wrong_password']
    # Prefer an unused relevant fact, but retain answers to repeated questions.
    relevant = [(i, f) for topic in topics for i, f in enumerate(available) if f['topic'] == topic]
    if relevant:
        index, fact = next(((i, f) for i, f in relevant if i not in used), relevant[0])
        used.add(index)
        return fact['answer'], fact['topic']
    return 'I do not know.', None

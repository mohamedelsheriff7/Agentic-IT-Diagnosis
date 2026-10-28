
import json
import re
from copy import deepcopy
from pathlib import Path

from .history import load_historical_tickets, retrieve_similar_tickets
from .knowledge import get_next_questions, search_articles, get_article_by_id, get_resolution_guidance
from .models import (
    DiagnosisCandidate,
    DiagnosticResult,
    DiagnosticState,
    DiagnosticStep,
    Evidence,
    TicketInput,
)
from .answers import (interpret_answer, question_family, uncertain, collected_facts,
                      question_answered, diagnostic_findings, reported_pattern, canonical_question)

# Resolve data paths relative to the repository, independent of the current directory.
_AGENT_DIR = Path(__file__).resolve().parent
_ADK_ROOT = _AGENT_DIR.parents[1]
_KNOWLEDGE_DIR = _ADK_ROOT / "knowledge"
_DEFAULT_HISTORY_FILE = _KNOWLEDGE_DIR / "historical_tickets.json"
_DEFAULT_ARTICLES_FILE = _KNOWLEDGE_DIR / "diagnostic_articles.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ticket_text(ticket: TicketInput) -> str:
    """Combine ticket text for simple keyword-based rules."""
    return f"{ticket.summary} {ticket.description}".lower()


def _is_critical_priority(ticket: TicketInput) -> bool:
    """Recognize common representations of critical priority."""
    priority = str(ticket.priority).strip().lower()
    severity = str(ticket.severity or "").strip().lower()
    return (
        priority in {"1", "p1", "critical", "highest"}
        or severity in {"1", "p1", "critical"}
    )


def _requires_human_escalation(ticket: TicketInput) -> bool:
    """Apply mandatory escalation rules before diagnosis."""
    return (
        ticket.security_sensitive
        or ticket.privileged_access
        or _is_critical_priority(ticket)
        or _reported_credential_exposure(_ticket_text(ticket))
        or bool(ticket.metadata.get('reported_security_evidence_ids'))
    )


def _reported_credential_exposure(text: str) -> bool:
    """A reported credential disclosure requires review even if intake flags omit it.

    This identifies a safety concern, never a confirmed security diagnosis.
    """
    return bool(re.search(r'(typed|entered|submitted|gave|shared).{0,70}(password|credentials)', text, re.I)
        and re.search(r'fake|phish|suspicious|fraud|untrusted', text, re.I))


# ---------------------------------------------------------------------------
# Step 2: Expanded initial candidate generation (English + Arabic keywords)
# ---------------------------------------------------------------------------

def _initial_candidates(ticket: TicketInput) -> list[DiagnosisCandidate]:
    """Generate initial hypotheses from the reported symptoms.

    Covers all 21+ taxonomy codes including Arabic and Franco-Arabic keywords.
    Each rule adds at most one candidate per diagnosis_id; keyword sets are
    deliberately non-overlapping across mutually exclusive diagnoses.
    """
    text = _ticket_text(ticket)
    candidates: list[DiagnosisCandidate] = []
    seen_ids: set[str] = set()

    def add(
        diagnosis_id: str,
        name: str,
        domain: str,
        category: str,
        resolver_group: str,
        required_evidence: list[str],
    ) -> None:
        if diagnosis_id not in seen_ids:
            seen_ids.add(diagnosis_id)
            candidates.append(
                DiagnosisCandidate(
                    diagnosis_id=diagnosis_id,
                    name=name,
                    domain=domain,
                    category=category,
                    resolver_group=resolver_group,
                    required_evidence=required_evidence,
                )
            )

    # ---- Security threats — must be checked first (highest priority) -------

    # PHISHING (en + ar: تصيّد, رابط مشبوه, phishing, suspicious email/link)
    if any(w in text for w in (
        "phishing", "suspicious email", "suspicious link", "credential harvesting",
        "spoofed", "urgent link", "malicious attachment",
        "تصيد", "تصيّد", "رسالة مشبوهة", "رابط مشبوه",
    )):
        add("PHISHING", "Suspected phishing", "Security", "Threat",
            "GRP-SEC", ["phishing_confirmed"])

    # MALWARE (en + ar: برمجية خبيثة, ransomware, malware, virus)
    if any(w in text for w in (
        "malware", "ransomware", "virus", "trojan", "suspicious behavior",
        "security alert", "files encrypted", "endpoint compromised",
        "برمجية خبيثة", "فيروس", "اختراق", "مشبوه",
    )):
        add("MALWARE", "Suspected malware", "Security", "Threat",
            "GRP-SEC", ["malware_confirmed"])

    # DATA_EXPOSURE (en + ar: كشف بيانات, data exposure, sensitive data)
    if any(w in text for w in (
        "data exposure", "sensitive data", "wrong recipient", "shared publicly",
        "unintended sharing", "data leak",
        "كشف بيانات", "بيانات حساسة", "مشاركة خاطئة",
    )):
        add("DATA_EXPOSURE", "Suspected data exposure", "Security", "Data Protection",
            "GRP-SEC", ["data_exposure_confirmed"])

    # ---- Access Management: security-policy lockout (before ordinary lockout) --

    # ACCOUNT_LOCKED_POLICY (en + ar: سياسة أمنية, security policy lock)
    if any(w in text for w in (
        "security policy", "suspicious activity", "suspicious sign-in",
        "risk-based", "identity risk", "security lock",
        "سياسة أمنية", "نشاط مشبوه", "تنبيه أمني",
    )):
        add("ACCOUNT_LOCKED_POLICY", "Account locked by security policy",
            "Access Management", "Authentication", "GRP-SEC",
            ["security_policy_lock_confirmed"])

    # ---- Access Management: authentication ------------------------------------

    # ACCOUNT_LOCKED (en + ar: الحساب اتقفل, account locked)
    if any(w in text for w in (
        "locked out", "account locked", "account is locked", "lockout",
        "الحساب اتقفل", "الحساب مقفل", "تم قفل الحساب",
    )):
        add("ACCOUNT_LOCKED", "Account lockout", "Access Management", "Authentication",
            "IAM Team", ["account_lockout_confirmed"])

    # STALE_CREDENTIALS / PASSWORD_EXPIRED (en + ar: كلمة المرور انتهت)
    if any(w in text for w in (
        "old password", "saved password", "saved credentials",
        "password expired", "password expiry", "password has expired",
        "كلمة المرور انتهت", "انتهت صلاحية كلمة المرور", "تغيير كلمة المرور",
        "الباسورد منتهي",
    )):
        add("PASSWORD_EXPIRED", "Expired password", "Access Management", "Authentication",
            "IAM Team", ["password_expired_confirmed"])
        # Legacy code also used STALE_CREDENTIALS; keep it if the text is stale-specific
        if any(w in text for w in ("old password", "saved password", "saved credentials")):
            add("STALE_CREDENTIALS", "Outdated saved credentials",
                "Access Management", "Authentication", "IAM Team",
                ["stale_credentials_confirmed"])

    # MFA_FAILURE (en + ar: مشكلة MFA, التحقق, رمز التحقق)
    if any(w in text for w in (
        "mfa", "multi-factor", "multifactor", "changed my phone", "new phone",
        "authenticator", "verification code", "otp", "one-time password",
        "مشكلة mfa", "مشكلة التحقق", "رمز التحقق", "المصادقة الثنائية",
        "التحقق المزدوج",
    )):
        add("MFA_FAILURE", "Multi-factor authentication problem",
            "Access Management", "Authentication", "IAM Team",
            ["mfa_failure_confirmed"])

    # ACCOUNT_DISABLED (en + ar: حساب معطّل, disabled, deactivated)
    if any(w in text for w in (
        "account disabled", "account deactivated", "account suspended",
        "disabled account",
        "الحساب معطّل", "الحساب متوقف", "الحساب مغلق",
    )):
        add("ACCOUNT_DISABLED", "Disabled account", "Access Management", "Authentication",
            "IAM Team", ["account_disabled_confirmed"])

    # PRIVILEGED_ACCESS (en + ar: صلاحيات مرتفعة, admin access)
    if any(w in text for w in (
        "admin access", "administrator access", "elevated access",
        "privileged access", "root access", "sudo", "domain admin",
        "صلاحيات إدارية", "صلاحيات مرتفعة", "وصول مميز",
    )):
        add("PRIVILEGED_ACCESS", "Privileged-access request",
            "Access Management", "Privileges", "IAM Team",
            ["privileged_access_review_required"])

    # ---- Access Management: authorization ------------------------------------

    # MISSING_ENTITLEMENT (en + ar: صلاحية مفقودة, access denied, permission)
    if any(w in text for w in (
        "access denied", "cannot access", "can't access", "unable to access",
        "permission", "missing role", "missing entitlement",
        "لا توجد صلاحية", "وصول مرفوض", "صلاحية مفقودة", "ما عندي صلاحية",
    )):
        add("MISSING_ENTITLEMENT", "Missing application entitlement",
            "Application", "Authorization", "Application Support",
            ["entitlement_missing_confirmed"])

    # ---- Application symptoms -----------------------------------------------

    # APP_AUTH_FAILURE (one app fails, others work — en + ar)
    if any(w in text for w in (
        "sso", "single sign-on", "single sign on", "application authentication",
        "app authentication", "session expired", "token expired",
        "مشكلة تسجيل الدخول للتطبيق", "خطأ مصادقة التطبيق",
    )):
        add("APP_AUTH_FAILURE", "Application authentication failure",
            "Application", "Authentication", "Application Support",
            ["app_auth_failure_confirmed"])

    # APP_OUTAGE / APPLICATION_FAILURE (service unavailable, error 500, down)
    if any(w in text for w in (
        "application down", "app is down", "service unavailable",
        "unavailable", "error 500", "http 500", "http 503", "outage",
        "التطبيق متوقف", "الخدمة غير متاحة", "توقف التطبيق",
    )):
        add("APP_OUTAGE", "Application or service outage",
            "Application", "Availability", "Application Support",
            ["application_failure_confirmed"])
        # Legacy alias kept for backward compatibility
        add("APPLICATION_FAILURE", "Application or service failure",
            "Application", "Availability", "Application Support",
            ["application_failure_confirmed"])

    # APP_ERROR (app opens but action fails — en + ar)
    if any(w in text for w in (
        "error code", "application error", "throws an error", "fails during",
        "unexpected error", "unhandled exception",
        "خطأ في التطبيق", "التطبيق يعطي خطأ",
    )):
        add("APP_ERROR", "Application execution error",
            "Application", "Execution", "Application Support",
            ["app_error_confirmed"])

    # SYNC_DELAY (en + ar: تأخر مزامنة)
    if any(w in text for w in (
        "sync", "synchronization", "not syncing", "sync delay", "sync lag",
        "out of sync", "data not updated",
        "تأخر مزامنة", "المزامنة لا تعمل", "البيانات لم تتحدث",
    )):
        add("SYNC_DELAY", "Application synchronization delay",
            "Application", "Synchronization", "Application Support",
            ["sync_delay_confirmed"])

    # ---- Network symptoms ----------------------------------------------------

    # VPN_OUTAGE (multiple users, shared gateway — check before VPN_CLIENT_ISSUE)
    if any(w in text for w in (
        "vpn outage", "vpn down", "vpn not working for everyone",
        "vpn gateway", "multiple users vpn",
        "خدمة vpn متوقفة", "انقطاع vpn", "vpn للجميع",
    )):
        add("VPN_OUTAGE", "VPN outage", "Network", "VPN",
            "GRP-NET", ["vpn_outage_confirmed"])

    # VPN_CLIENT_ISSUE (one user — en + ar: مشكلة vpn, vpn لا يتصل)
    if any(w in text for w in (
        "vpn", "cannot connect to vpn", "can't connect to vpn", "vpn error",
        "vpn client", "vpn configuration",
        "مشكلة vpn", "vpn لا يتصل", "الاتصال بـ vpn", "في بي ان",
    )):
        add("VPN_CLIENT_ISSUE", "VPN client or credential issue",
            "Network", "VPN", "GRP-NET", ["vpn_client_issue_confirmed"])

    # WIFI_FAILURE (en + ar: مشكلة واي فاي, wifi)
    if any(w in text for w in (
        "wifi", "wi-fi", "wireless", "cannot connect to wifi",
        "wifi disconnects", "no wifi",
        "واي فاي", "مشكلة wifi", "الشبكة اللاسلكية",
    )):
        add("WIFI_FAILURE", "Wi-Fi association failure",
            "Network", "Connectivity", "GRP-NET",
            ["wifi_failure_confirmed"])

    # DNS_FAILURE (en + ar: أسماء المواقع لا تعمل, dns, name resolution)
    if any(w in text for w in (
        "dns", "name resolution", "server not found", "cannot resolve",
        "hostname", "internal name",
        "أسماء المواقع", "حل الأسماء", "dns لا يعمل",
    )):
        add("DNS_FAILURE", "DNS lookup failure",
            "Network", "DNS", "GRP-NET", ["dns_failure_confirmed"])

    # ---- Endpoint symptoms ---------------------------------------------------

    # PRINTER_OFFLINE (en + ar: الطابعة غير متصلة)
    if any(w in text for w in (
        "printer", "print", "printing", "print job", "printer offline",
        "طابعة", "الطباعة", "الطابعة", "طباعة",
    )):
        add("PRINTER_OFFLINE", "Printer offline",
            "Endpoints", "Printing", "GRP-END",
            ["printer_offline_confirmed"])

    # DISK_FULL (en + ar: مساحة ممتلئة, disk full, low disk)
    if any(w in text for w in (
        "disk full", "low disk", "disk space", "storage full", "no space",
        "out of space", "storage warning",
        "مساحة ممتلئة", "القرص ممتلئ", "مساحة التخزين",
    )):
        add("DISK_FULL", "Endpoint disk full",
            "Endpoints", "Storage", "GRP-END",
            ["disk_full_confirmed"])

    # LOCAL_ENDPOINT (en + ar: مشكلة محلية, device issue)
    if any(w in text for w in (
        "my laptop", "my device", "my computer", "my pc", "my machine",
        "only on my", "local issue", "device issue",
        "no sound", "speakers", "audio output", "microphone", "browser zoom", "page zoom",
        "keyboard layout", "brightness", "second monitor", "display mode", "bluetooth",
        "camera preview", "camera shutter", "notification", "do not disturb",
        "جهازي", "اللابتوب", "الكمبيوتر", "مشكلة في الجهاز",
    )):
        add("LOCAL_ENDPOINT", "Local endpoint issue",
            "Endpoints", "Device", "GRP-END",
            ["local_endpoint_confirmed"])

    # ---- Infrastructure symptoms --------------------------------------------

    # SERVER_FAILURE (en + ar: السيرفر لا يعمل, server down)
    if any(w in text for w in (
        "server down", "server failure", "server unreachable", "server error",
        "infrastructure", "host unavailable",
        "السيرفر لا يعمل", "الخادم متوقف", "مشكلة سيرفر",
    )):
        add("SERVER_FAILURE", "Server failure",
            "Infrastructure", "Compute", "GRP-INFRA",
            ["server_failure_confirmed"])

    # CERT_EXPIRED (en + ar: شهادة منتهية, certificate expired)
    if any(w in text for w in (
        "certificate expired", "cert expired", "certificate error",
        "ssl error", "tls error", "invalid certificate",
        "شهادة منتهية", "خطأ شهادة", "شهادة غير صالحة",
    )):
        add("CERT_EXPIRED", "Certificate expired",
            "Infrastructure", "Certificates", "GRP-INFRA",
            ["cert_expired_confirmed"])

    # STORAGE_FAILURE (shared storage — en + ar)
    if any(w in text for w in (
        "shared drive", "network drive", "shared storage", "file share",
        "storage service",
        "مشكلة التخزين المشترك", "محرك الشبكة",
    )):
        add("STORAGE_FAILURE", "Shared storage failure",
            "Infrastructure", "Storage", "GRP-INFRA",
            ["storage_failure_confirmed"])

    # ---- Catch-all: vague descriptions, Arabic general complaints -----------

    # REQUEST_GUIDANCE — "how do I", "how to" guidance requests
    if any(w in text for w in (
        "how do i", "how to", "instructions", "guide me",
        "كيف", "ارشادات", "خطوات", "طريقة",
    )) and not any(w in text for w in ("cannot", "error", "fail", "not working")):
        add("REQUEST_GUIDANCE", "General guidance request",
            "Service Desk", "How To", "GRP-L1",
            ["guidance_provided"])

    # UNKNOWN_CAUSE fallback — vague reports or truly unmatched tickets
    if not candidates or (
        len(candidates) == 1 and candidates[0].diagnosis_id == "REQUEST_GUIDANCE"
    ):
        add(
            "UNKNOWN_ISSUE",
            "Cause not yet identified",
            ticket.domain or "Other",
            ticket.category or "Unclassified",
            "Service Desk L1",
            ["cause_identified"],
        )

    return candidates


# ---------------------------------------------------------------------------
# Trace helper
# ---------------------------------------------------------------------------

def _add_trace(
    state: DiagnosticState,
    event_type: str,
    description: str,
    rationale: str | None = None,
    evidence_ids: list[str] | None = None,
    candidate_ids: list[str] | None = None,
) -> None:
    """Append a numbered event to the diagnostic trace."""
    state.trace.append(
        DiagnosticStep(
            step_number=len(state.trace) + 1,
            event_type=event_type,
            description=description,
            evidence_ids=evidence_ids or [],
            candidate_ids=candidate_ids or [],
            rationale=rationale,
        )
    )


# ---------------------------------------------------------------------------
# Knowledge + history retrieval
# ---------------------------------------------------------------------------

def _retrieve_context(
    state: DiagnosticState,
    articles_path: str | Path,
    history_path: str | Path,
    history_limit: int = 5,
    knowledge_limit: int = 5,
    knowledge_only: bool = False,
) -> None:
    """Attach approved knowledge and resolved-ticket matches as advisory context.

    Retrieval never confirms a diagnosis. Historical outcomes are analogies, not proof.
    """
    observations = ' '.join(str(e.value) for e in state.evidence if e.source == 'user_answer')
    query = f"{state.ticket.summary} {state.ticket.description} {observations}".strip()

    try:
        articles = search_articles(query, limit=knowledge_limit, path=articles_path,
            approved_only=not state.ticket.metadata.get('diagnostic_review_mode', False),
            diagnosis_codes={c.diagnosis_id for c in state.candidates}
                if state.ticket.metadata.get('diagnostic_review_mode') else None)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        articles = []
        _add_trace(
            state,
            event_type="knowledge_retrieval_unavailable",
            description="Approved diagnostic knowledge could not be retrieved.",
            rationale=f"Knowledge retrieval error: {type(exc).__name__}: {exc}",
        )

    if state.ticket.metadata.get('diagnostic_review_mode'):
        relevant_codes = {c.diagnosis_id for c in state.candidates}
        articles = [a for a in articles if a['article'].get('diagnosis_code') in relevant_codes]
    state.knowledge_matches = [
        {
            "article_id": item["article_id"],
            "title": item["title"],
            "score": item["score"],
            "matched_terms": item["matched_terms"],
            "diagnosis_code": item["article"].get("diagnosis_code"),
            "questions": get_next_questions(item["article"]),
            "approved": item['article'].get('approved') is True,
            "usage": 'DIAGNOSTIC_GUIDANCE',
            "version": item['article'].get('version'),
            "backend_reference": not state.ticket.metadata.get('diagnostic_review_mode', False),
            "source": 'BUNDLED_DIAGNOSTIC_KNOWLEDGE',
            **({'self_service_guidance': {
                'article_id': item['article_id'], 'title': item['article'].get('title'),
                'scenario_code': item['article'].get('scenario_code'),
                'eligibility_evidence': item['article'].get('required_evidence', []),
                'steps': item['article'].get('resolution_steps', []),
                'success_criteria': item['article'].get('success_criteria', []),
                'stop_conditions': item['article'].get('exclusion_criteria', []),
                'backend_registered': False, 'authorizes_ticket_resolution': False,
                'execution_status': 'NOT_EXECUTED',
            }} if item['article'].get('guided_self_service') else {}),
        }
        for item in articles
    ]
    _add_trace(
        state,
        event_type="knowledge_retrieved",
        description=f"Retrieved {len(articles)} diagnostic article(s).",
        rationale=(
            "Drafts may guide questions in diagnostic review mode; they never authorize a fix. "
            "Retrieval relevance is not diagnostic confidence."
        ),
        candidate_ids=[
            str(item["article"].get("diagnosis_code"))
            for item in articles if item["article"].get("diagnosis_code")
        ],
    )

    if knowledge_only:
        for candidate in state.candidates:
            candidate.knowledge_article_id = next((m['article_id'] for m in state.knowledge_matches
                if m.get('diagnosis_code') == candidate.diagnosis_id and m.get('approved')), None)
        return
    try:
        historical = load_historical_tickets(history_path)
        matches = retrieve_similar_tickets(
            state.ticket, historical, limit=history_limit
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        matches = []
        _add_trace(
            state,
            event_type="history_retrieval_unavailable",
            description="Historical ticket retrieval could not be completed.",
            rationale=f"History retrieval error: {type(exc).__name__}: {exc}",
        )

    state.historical_matches = [
        {
            "ticket_id": match.historical_ticket.ticket.ticket_id,
            "score": round(match.score, 4),
            "matched_on": match.matched_on,
            "diagnosis_code": match.historical_ticket.diagnosis_code,
            "resolution_summary": match.historical_ticket.resolution_summary,
            "owner_group_id": match.historical_ticket.owner_group_id,
        }
        for match in matches
    ]
    _add_trace(
        state,
        event_type="historical_tickets_retrieved",
        description=(
            f"Retrieved {len(matches)} similar resolved/closed historical ticket(s)."
        ),
        rationale=(
            "Past outcomes are supporting context only and do not prove the current "
            "ticket has the same cause."
        ),
        candidate_ids=[
            str(match.historical_ticket.diagnosis_code)
            for match in matches if match.historical_ticket.diagnosis_code
        ],
    )

    # Approved knowledge can contribute diagnostic hypotheses and their questions.
    existing_ids = {candidate.diagnosis_id for candidate in state.candidates}
    for item in articles:
        article = item["article"]
        if article.get('approved') is not True:
            continue  # Draft guidance cannot introduce policy actions or unrelated hypotheses.
        diagnosis_id = article.get("diagnosis_code")
        if not diagnosis_id or diagnosis_id in existing_ids:
            continue
        state.candidates.append(
            DiagnosisCandidate(
                diagnosis_id=str(diagnosis_id),
                name=str(article.get("title") or diagnosis_id.replace("_", " ").title()),
                domain=str(article.get("domain") or state.ticket.domain or "Other"),
                category=str(article.get("category") or state.ticket.category or "Unclassified"),
                resolver_group=str(article.get("resolver_group_id") or "Service Desk L1"),
                required_evidence=article.get("required_evidence", []),
                knowledge_article_id=item["article_id"],
            )
        )
        existing_ids.add(str(diagnosis_id))
        _add_trace(
            state,
            event_type="knowledge_hypothesis_added",
            description=f"Added {diagnosis_id} as a candidate from approved article {item['article_id']}.",
            rationale="Approved knowledge provides a hypothesis; current-ticket evidence is still required.",
            candidate_ids=[str(diagnosis_id)],
        )

    # Similar historical outcomes can add hypotheses, never final diagnoses.
    for match in matches:
        past = match.historical_ticket
        diagnosis_id = past.diagnosis_code
        if not diagnosis_id or diagnosis_id in existing_ids or match.score < 0.15:
            continue
        past_ticket = past.ticket
        state.candidates.append(
            DiagnosisCandidate(
                diagnosis_id=diagnosis_id,
                name=diagnosis_id.replace("_", " ").title(),
                domain=past_ticket.domain or "Other",
                category=past_ticket.category or "Unclassified",
                resolver_group=past.owner_group_id or "Service Desk L1",
                required_evidence=["diagnosis_confirmed_by_current_ticket_evidence"],
            )
        )
        existing_ids.add(diagnosis_id)
        _add_trace(
            state,
            event_type="historical_hypothesis_added",
            description=(
                f"Added {diagnosis_id} as a candidate based on a similar historical ticket."
            ),
            rationale=(
                f"Historical similarity score={match.score:.3f}; this remains a "
                "hypothesis and requires evidence from the current ticket."
            ),
            candidate_ids=[diagnosis_id],
        )

    # Attach only approved articles that match a candidate's diagnosis code.
    article_by_diagnosis = {
        item["article"].get("diagnosis_code"): item["article_id"]
        for item in articles if item["article"].get("diagnosis_code")
    }
    for candidate in state.candidates:
        if candidate.knowledge_article_id is None:
            candidate.knowledge_article_id = article_by_diagnosis.get(candidate.diagnosis_id)


# ---------------------------------------------------------------------------
# Investigation entry point
# ---------------------------------------------------------------------------

def start_investigation(
    ticket: TicketInput,
    *,
    articles_path: str | Path = _DEFAULT_ARTICLES_FILE,
    history_path: str | Path = _DEFAULT_HISTORY_FILE,
) -> DiagnosticState:
    """Create an initial state for a newly received ticket."""
    state = DiagnosticState(ticket=ticket)

    state.candidates = _initial_candidates(ticket)
    _retrieve_context(state, articles_path=articles_path, history_path=history_path)

    _add_trace(
        state,
        event_type="investigation_started",
        description="Created initial diagnostic hypotheses from ticket symptoms.",
        rationale="Keyword rules suggest hypotheses; they do not prove a diagnosis.",
        candidate_ids=[c.diagnosis_id for c in state.candidates],
    )

    if _requires_human_escalation(ticket):
        state.recommended_action = "escalate"
        state.status = "escalated"
        state.rationale = (
            "Mandatory human escalation applies because the ticket is "
            "security-sensitive, involves privileged access, or has "
            "critical priority."
        )
        _add_trace(
            state,
            event_type="mandatory_escalation",
            description="Investigation requires human handling.",
            rationale=state.rationale,
        )
        return state

    # Step 7: run outage check immediately — if shared-service signals exist,
    # signal escalation so the Supervisor can route to the Escalation agent.
    _check_outage_signal(state)
    if state.status == "escalated":
        return state

    state.recommended_action = "investigate"
    state.status = "in_progress"
    state.next_question = choose_next_question(state)
    if state.next_question:
        state.questions_asked.append(state.next_question)
        _add_trace(
            state,
            event_type="question_selected",
            description=state.next_question,
            rationale="The answer may help distinguish between plausible causes.",
            candidate_ids=[c.diagnosis_id for c in state.candidates],
        )

    return state


# ---------------------------------------------------------------------------
# Step 7: Outage signal detection
# ---------------------------------------------------------------------------

# Diagnosis IDs whose presence indicates a potential shared-service issue.
_OUTAGE_CANDIDATE_IDS = frozenset({
    "VPN_OUTAGE", "APP_OUTAGE", "APPLICATION_FAILURE",
    "SERVER_FAILURE", "STORAGE_FAILURE",
})


def _check_outage_signal(state: DiagnosticState) -> None:
    """Set escalate if shared-service candidates are present.

    This is a local signal only — it does not call count_recent_tickets() or
    find_open_global_tickets() (those require the backend and are called from
    integrated.py).  It surfaces the signal so the Supervisor can route to the
    Escalation & Outage agent before individual remediation.
    """
    outage_candidates = [
        c for c in state.candidates
        if c.diagnosis_id in _OUTAGE_CANDIDATE_IDS
    ]
    if not outage_candidates:
        if (state.status == 'escalated'
                and (state.rationale or '').startswith('Shared-service candidate(s) detected:')
                and not _requires_human_escalation(state.ticket)):
            state.status = 'in_progress'
            state.recommended_action = 'investigate'
            state.next_question = None
            state.rationale = 'The previous outage hypothesis was excluded by current evidence. Continue individual diagnosis.'
            _add_trace(state, event_type='outage_signal_cleared', description=state.rationale,
                rationale='No active shared-service candidate remains; the earlier outage recommendation is superseded.',
                candidate_ids=[c.diagnosis_id for c in state.candidates])
        return

    outage_ids = [c.diagnosis_id for c in outage_candidates]
    # A prior individual conclusion cannot remain actionable while the same
    # ticket requires shared-service screening.
    if state.final_diagnosis:
        state.final_diagnosis = None
        state.confidence = None
        state.ticket.metadata.pop('diagnosis_basis', None)
    state.recommended_action = "escalate"
    state.status = "escalated"
    state.next_question = None
    state.rationale = (
        f"Shared-service candidate(s) detected: {', '.join(outage_ids)}. "
        "Returning ESCALATE so the Supervisor can run outage screening "
        "(count_recent_tickets / find_open_global_tickets) before individual "
        "diagnosis proceeds."
    )
    conflicts = [c for c in outage_candidates if c.supporting_evidence_ids and c.contradicting_evidence_ids]
    if conflicts:
        state.rationale += (
            ' Current evidence conflicts: supporting observations challenge an earlier exclusion. '
            'Both supporting and contradicting observations are retained. The Supervisor '
            'must review current health and recent tickets for the same CI/location. '
            'An outage is not confirmed and no global ticket or link has been created.'
        )
    evidence_ids = sorted({eid for c in outage_candidates for eid in
        c.supporting_evidence_ids + c.contradicting_evidence_ids})
    if (state.trace and state.trace[-1].event_type == 'outage_signal_detected'
            and state.trace[-1].description == state.rationale
            and state.trace[-1].candidate_ids == outage_ids
            and state.trace[-1].evidence_ids == evidence_ids):
        return
    _add_trace(
        state,
        event_type="outage_signal_detected",
        description=state.rationale,
        rationale=(
            "An active shared-service hypothesis requires scoped screening; this signal "
            "does not establish an outage or authorize a global-incident action."
        ),
        candidate_ids=outage_ids,
        evidence_ids=evidence_ids,
    )


# ---------------------------------------------------------------------------
# Question selection
# ---------------------------------------------------------------------------

def choose_next_question(state: DiagnosticState) -> str | None:
    """Select the next unused question, prioritizing higher-ranked candidates."""
    if not state.candidates:
        return None

    ranked_ids = [item["diagnosis_id"] for item in rank_candidates(state)]

    # Built-in discriminating questions per diagnosis code.
    question_bank: dict[str, list[str]] = {
        "ACCOUNT_LOCKED": [
            "What exact sign-in message do you see?",
            "Does the sign-in screen currently report that the account is locked?",
            "Did you receive a security alert or suspicious-activity notice before the lockout?",
        ],
        "STALE_CREDENTIALS": [
            "Does the problem continue after you update the saved password "
            "on the device or mail application?",
            "Does the sign-in error explicitly say the password has expired?",
        ],
        "PASSWORD_EXPIRED": [
            "Does the sign-in screen explicitly say the password has expired?",
            "Can you access other corporate applications with the same account?",
        ],
        "MFA_FAILURE": [
            "Can you receive and approve the verification prompt on your "
            "current phone?",
            "Does the identity provider show a failed or unregistered MFA method?",
        ],
        "MISSING_ENTITLEMENT": [
            "Can you access other corporate applications with the same account?",
            "Has the application owner confirmed that your account has the required role?",
        ],
        "APP_AUTH_FAILURE": [
            "Do other corporate applications accept the same account while this one fails?",
            "Does the application show an SSO or session error rather than a password error?",
        ],
        "APPLICATION_FAILURE": [
            "Are other users experiencing the same application error?",
            "Does the service health check report an active incident?",
        ],
        "APP_OUTAGE": [
            "Are multiple users at the same location affected by this application issue?",
            "Does the service health report the application as unavailable or degraded?",
        ],
        "APP_ERROR": [
            "Does the application open successfully but fail only when you perform a specific action?",
            "Do colleagues using the same function see the same error?",
        ],
        "SYNC_DELAY": [
            "Are all records delayed or only specific records?",
            "Is the source system showing the updated data while the destination remains stale?",
        ],
        "ACCOUNT_DISABLED": [
            "Does the sign-in message explicitly say your account is disabled or deactivated?",
            "Is the account expected to be active based on your current role in the organization?",
        ],
        "ACCOUNT_LOCKED_POLICY": [
            "Did you receive a security alert or suspicious-activity notice before the lockout?",
            "Does the identity provider indicate a security-policy lock reason?",
        ],
        "PRIVILEGED_ACCESS": [
            "What exact task requires elevated access, and for how long?",
            "Is the requested access a standard application role or a privileged/admin role?",
        ],
        "VPN_CLIENT_ISSUE": [
            "Can colleagues at the same site connect to VPN right now?",
            "Does the VPN client show a local configuration or credential error?",
        ],
        "VPN_OUTAGE": [
            "Are multiple users at the same site unable to connect to VPN within a short time window?",
            "Can affected users reach other internet services, and does VPN health show UNAVAILABLE?",
        ],
        "WIFI_FAILURE": [
            "Can another device connect to the same Wi-Fi at the same location?",
            "Can this device connect to a different approved network?",
        ],
        "DNS_FAILURE": [
            "Do internal hostnames fail while direct IP access to the same server works?",
            "Do external websites resolve normally, or does all connectivity fail?",
        ],
        "PRINTER_OFFLINE": [
            "Is only one user affected or everyone using the same printer?",
            "Can the printer be reached by other users on the same network?",
        ],
        "DISK_FULL": [
            "Is the storage warning on one device or are multiple users seeing a shared storage error?",
            "Does the storage check show low free space on the endpoint, or is a network drive affected?",
        ],
        "LOCAL_ENDPOINT": [
            "Does the same task work on another device or for a colleague?",
            "Is the affected service reported as healthy for other users?",
        ],
        "SERVER_FAILURE": [
            "Are multiple users or services affected, or only one application function?",
            "Does infrastructure health show an unavailable host or dependency?",
        ],
        "CERT_EXPIRED": [
            "Does the browser warning show an expired certificate, or an untrusted/hostname mismatch?",
            "Are multiple users seeing the same certificate warning on the same service?",
        ],
        "STORAGE_FAILURE": [
            "Is the problem a local device disk warning or a shared drive used by multiple users?",
            "Can users read existing files but not write, or is the share entirely unavailable?",
        ],
        "PHISHING": [
            "Did you click the link, open the attachment, or enter any credentials?",
            "Does the message request credentials, payment, or create unusual urgency?",
        ],
        "MALWARE": [
            "Did an approved security tool show an alert, or is the report based on unusual behavior?",
            "Are files being encrypted, security tools disabled, or unexpected prompts appearing?",
        ],
        "DATA_EXPOSURE": [
            "What type of data may have been exposed, and when was it shared?",
            "Was the recipient or link authorized, and has the exposure been contained?",
        ],
        "REQUEST_GUIDANCE": [
            "Are you asking for setup instructions, or is an existing service failing with an error?",
            "Which approved device or application and which step are you trying to complete?",
        ],
        "UNKNOWN_CAUSE": [
            "What exact error message do you see, and when did the problem start?",
            "Which application or device were you using when you noticed the problem?",
        ],
        "UNKNOWN_ISSUE": [
            "What exact error message do you see, and when did the problem start?",
            "Which application or device were you using when you noticed the problem?",
        ],
    }

    questions: list[str] = []
    for diagnosis_id in ranked_ids:
        article_questions = []
        for article_match in state.knowledge_matches:
            if article_match.get('diagnosis_code') == diagnosis_id:
                article_questions.extend(article_match.get('questions', []))
        built_in = question_bank.get(str(diagnosis_id), [])
        questions.extend(built_in + article_questions if state.ticket.metadata.get('diagnostic_review_mode')
                         else article_questions + built_in)

    # Deduplicate while preserving order; skip already-asked questions.
    seen: set[str] = set()
    for question in questions:
        question = canonical_question(question)
        if question in seen:
            continue
        seen.add(question)
        family = question_family(question)
        if family and any(question_family(previous) == family for previous in state.questions_asked):
            continue
        if question not in state.questions_asked and not question_answered(question, collected_facts(state)):
            _add_trace(state, event_type='next_question_selected', description=question,
                rationale='Distinguish remaining hypotheses using an unanswered observation; known scoped facts are skipped.',
                candidate_ids=[str(code) for code in ranked_ids])
            return question

    return None


# ---------------------------------------------------------------------------
# Diagnosis confirmation
# ---------------------------------------------------------------------------

def _try_confirm_diagnosis(state: DiagnosticState) -> bool:
    """Apply a conservative evidence threshold without executing a fix.

    Requires corroboration including an actual diagnostic_check observation.
    Repeated user assertions alone cannot establish a diagnosis or authorize a fix.
    """
    if _requires_human_escalation(state.ticket) or state.ticket.metadata.get('pending_correction_review'):
        return False

    # Shared-service observations require Supervisor screening before an
    # individual diagnosis, even if another candidate otherwise qualifies.
    if any(c.diagnosis_id in _OUTAGE_CANDIDATE_IDS and c.supporting_evidence_ids
           for c in state.candidates):
        return False

    supported = []
    for candidate in state.candidates:
        if candidate.diagnosis_id in ("UNKNOWN_CAUSE", "UNKNOWN_ISSUE"):
            continue

        check_ids = {
            item.evidence_id
            for item in state.evidence
            if item.source == "diagnostic_check"
            and candidate.diagnosis_id in item.supports
            and candidate.diagnosis_id not in item.contradicts
        }
        answer_ids = {
            item.evidence_id
            for item in state.evidence
            if item.source == "user_answer"
            and candidate.diagnosis_id in item.supports
            and candidate.diagnosis_id not in item.contradicts
        }
        contradiction_count = sum(
            1 for item in state.evidence
            if candidate.diagnosis_id in item.contradicts
        )

        # A specific reported pattern can establish the symptom-level diagnosis.
        # This does not identify a faulty resolver/record or authorize resolution.
        if contradiction_count == 0 and (reported_pattern(state, candidate.diagnosis_id) or (len(check_ids) >= 1 and len(check_ids) + len(answer_ids) >= 2)):
            total = len(check_ids) + len(answer_ids)
            supported.append((candidate, total, len(check_ids)))

    # More than one qualifying candidate means ambiguity remains.
    if len(supported) != 1:
        return False

    candidate, total_count, check_count = supported[0]
    candidate.status = "confirmed"
    state.final_diagnosis = candidate.diagnosis_id

    # Heuristic ranking score: checks carry more weight than answers.
    state.confidence = round(min(0.95, 0.60 + 0.05 * check_count + 0.05 * total_count), 2)
    state.recommended_action = "route"
    state.status = "diagnosed"
    state.next_question = None
    state.ticket.metadata['diagnosis_basis'] = 'TOOL_CORROBORATED' if check_count else 'REPORTED_DIAGNOSTIC_PATTERN'
    state.rationale = (
        f"{candidate.diagnosis_id} is supported by {check_count} diagnostic-check "
        f"item(s) and {total_count - check_count} consistent user-answer item(s) "
        "with no contradictions. This heuristic confidence is not a calibrated "
        "probability. The case is recommended for routing; no fix was executed."
    )
    if not check_count:
        state.rationale = (f'Distinct reported observations match the retrieved guidance for {candidate.diagnosis_id} '
            'at the symptom-pattern level. The underlying faulty component remains unverified. '
            'Recommend routing with MEDIUM confidence; no repair or assignment was executed.')
    sources = [m['article_id'] for m in state.knowledge_matches if m.get('diagnosis_code') == candidate.diagnosis_id]
    if sources:
        state.rationale += ' Diagnostic guidance sources: ' + ', '.join(sources) + '. Guidance retrieval does not approve a repair.'
    _add_trace(
        state,
        event_type="diagnosis_supported",
        description=f"Evidence threshold met for {candidate.diagnosis_id}.",
        rationale=state.rationale,
        evidence_ids=sorted(candidate.supporting_evidence_ids),
        candidate_ids=[candidate.diagnosis_id],
    )
    return True


# ---------------------------------------------------------------------------
# Candidate ranking
# ---------------------------------------------------------------------------

def rank_candidates(state: DiagnosticState) -> list[dict[str, object]]:
    """Return a transparent evidence-weighted ranking of active candidates.

    Scores are heuristic ranking points, not probabilities.
    """
    source_weights = {
        "diagnostic_check": 2.0,
        "user_answer": 1.0,
        "ticket": 0.5,
    }
    ranked = []
    for candidate in state.candidates:
        support_items = [
            ev for ev in state.evidence
            if candidate.diagnosis_id in ev.supports
        ]
        contradiction_items = [
            ev for ev in state.evidence
            if candidate.diagnosis_id in ev.contradicts
        ]
        score = sum(source_weights.get(item.source, 0.25) for item in support_items)
        score -= sum(source_weights.get(item.source, 0.25) * 1.5 for item in contradiction_items)
        ranked.append({
            "diagnosis_id": candidate.diagnosis_id,
            "name": candidate.name,
            "score": round(score, 3),
            "supporting_evidence_ids": [item.evidence_id for item in support_items],
            "contradicting_evidence_ids": [item.evidence_id for item in contradiction_items],
            "knowledge_article_id": candidate.knowledge_article_id,
            "status": candidate.status,
        })
    return sorted(ranked, key=lambda item: (-float(item["score"]), str(item["diagnosis_id"])))


# ---------------------------------------------------------------------------
# Step 3: Answer normalisation and question→diagnosis mapping
# ---------------------------------------------------------------------------

def _normalise_yes_no(answer: str) -> str | None:
    """Normalize a short yes/no answer; leave ambiguous free text unclassified."""
    normalized = " ".join(answer.strip().lower().split()).strip(" .!?")
    if uncertain(normalized) or re.search(r'\b(?:ignore|pretend|override|assume)\b|تجاهل|افترض', normalized):
        return None
    if normalized in {"yes", "y", "yeah", "yep", "correct", "true", "i can", "i do",
                      "نعم", "أيوه", "ايوه", "اه", "صح"}:
        return "yes"
    if normalized in {"no", "n", "nope", "incorrect", "false", "i cannot", "i can't",
                      "i do not", "i don't", "لا", "لأ"}:
        return "no"
    # Accept an explicit answer followed by an explanation, without interpreting
    # embedded instructions or contradictory yes/no prefixes as observations.
    if not re.search(r'\b(?:ignore|pretend|override|assume)\b', normalized):
        prefix = re.match(r'^(yes|no|نعم|لا)(?:\s*[,،:—-]\s*|\s+)(.+)$', normalized)
        if prefix and not re.search(r'\b(?:yes|no)\b', prefix.group(2)):
            return 'yes' if prefix.group(1) in {'yes', 'نعم'} else 'no'
    return None


def _map_answer_to_diagnoses(question: str, answer: str) -> tuple[list[str], list[str]]:
    """Map answers to diagnosis supports/contradictions.

    Covers both built-in question strings and the discriminating_questions from
    knowledge articles (KB-001 to KB-026).  Each rule uses a *keyword substring*
    rather than exact match so minor rephrasing still works. Implemented natural
    observation families are interpreted first; other questions accept an explicit
    yes/no answer. Unclear text remains unknown.
    """
    interpreted = interpret_answer(question, answer)
    if interpreted:
        return interpreted['supports'], interpreted['contradicts']
    if question_family(question):
        return [], []
    polarity = _normalise_yes_no(answer)
    if polarity is None:
        return [], []

    q = question.lower()

    # ------------------------------------------------------------------
    # Password / credential rules
    # ------------------------------------------------------------------
    if "password has expired" in q or "sign-in error explicitly say" in q or "explicitly say the password expired" in q:
        return (["PASSWORD_EXPIRED", "STALE_CREDENTIALS"], []) if polarity == "yes" \
            else ([], ["PASSWORD_EXPIRED", "STALE_CREDENTIALS"])

    if "problem continue after you update the saved password" in q:
        return ([], ["STALE_CREDENTIALS"]) if polarity == "yes" \
            else (["STALE_CREDENTIALS"], [])

    # ------------------------------------------------------------------
    # MFA rules
    # ------------------------------------------------------------------
    if "failed or unregistered mfa method" in q or "identity provider show a failed" in q:
        return (["MFA_FAILURE"], []) if polarity == "yes" \
            else ([], ["MFA_FAILURE"])

    if "receive and approve the verification prompt" in q:
        return ([], ["MFA_FAILURE"]) if polarity == "yes" \
            else (["MFA_FAILURE"], [])

    if "password succeed before mfa" in q:
        # Yes = password is fine, MFA is the failing layer
        return (["MFA_FAILURE"], ["PASSWORD_EXPIRED", "STALE_CREDENTIALS"]) if polarity == "yes" \
            else (["PASSWORD_EXPIRED", "STALE_CREDENTIALS"], ["MFA_FAILURE"])

    if "recently replace" in q and ("phone" in q or "authenticator" in q):
        return (["MFA_FAILURE"], []) if polarity == "yes" \
            else ([], ["MFA_FAILURE"])

    # ------------------------------------------------------------------
    # Account lockout rules
    # ------------------------------------------------------------------
    if "still unable to sign in after the account was unlocked" in q:
        # Yes = unlock didn't help → may be a different issue
        return ([], ["ACCOUNT_LOCKED"]) if polarity == "yes" \
            else (["ACCOUNT_LOCKED"], [])

    if "confirmed the account" in q and "lock" in q:
        return (["ACCOUNT_LOCKED"], []) if polarity == "yes" \
            else ([], ["ACCOUNT_LOCKED"])

    if "security alert or suspicious-activity notice" in q or "suspicious sign-in" in q:
        return (["ACCOUNT_LOCKED_POLICY"], ["ACCOUNT_LOCKED"]) if polarity == "yes" \
            else ([], ["ACCOUNT_LOCKED_POLICY"])

    if "security-policy lock reason" in q:
        return (["ACCOUNT_LOCKED_POLICY"], ["ACCOUNT_LOCKED"]) if polarity == "yes" \
            else ([], ["ACCOUNT_LOCKED_POLICY"])

    # ------------------------------------------------------------------
    # Disabled account
    # ------------------------------------------------------------------
    if ("disabled" in q or "deactivated" in q) and "message" in q:
        return (["ACCOUNT_DISABLED"], ["ACCOUNT_LOCKED", "PASSWORD_EXPIRED"]) if polarity == "yes" \
            else ([], ["ACCOUNT_DISABLED"])

    if "expected to be active" in q:
        # No = might be terminated/lifecycle → still needs human, but confirms disabled
        return (["ACCOUNT_DISABLED"], []) if polarity == "no" \
            else ([], ["ACCOUNT_DISABLED"])

    # ------------------------------------------------------------------
    # Entitlement / app auth rules
    # ------------------------------------------------------------------
    if "access other corporate applications" in q:
        # Cached sessions mean success elsewhere is a clue, never a conclusive exclusion.
        if polarity == "yes":
            return (["MISSING_ENTITLEMENT", "APP_AUTH_FAILURE"], [])
        else:
            return (["PASSWORD_EXPIRED", "ACCOUNT_LOCKED", "MFA_FAILURE"], [])

    if "application owner confirmed" in q and "required role" in q:
        return (["MISSING_ENTITLEMENT"], []) if polarity == "no" \
            else ([], ["MISSING_ENTITLEMENT"])

    if "sso or session error" in q or "application show" in q and "sso" in q:
        return (["APP_AUTH_FAILURE"], ["PASSWORD_EXPIRED"]) if polarity == "yes" \
            else ([], ["APP_AUTH_FAILURE"])

    if "other corporate applications accept the same account" in q:
        return (["APP_AUTH_FAILURE", "MISSING_ENTITLEMENT"], []) if polarity == "yes" \
            else (["PASSWORD_EXPIRED", "ACCOUNT_LOCKED"], [])

    # ------------------------------------------------------------------
    # Application outage / failure rules
    # ------------------------------------------------------------------
    if "other users experiencing the same application error" in q or \
       "multiple users" in q and ("application" in q or "location" in q):
        return (["APPLICATION_FAILURE", "APP_OUTAGE"], []) if polarity == "yes" \
            else ([], ["APPLICATION_FAILURE", "APP_OUTAGE"])

    if "service health" in q and ("active incident" in q or "unavailable" in q or "degraded" in q):
        return (["APPLICATION_FAILURE", "APP_OUTAGE"], []) if polarity == "yes" \
            else ([], ["APPLICATION_FAILURE", "APP_OUTAGE"])

    if "application open" in q and "specific action" in q:
        return (["APP_ERROR"], ["APP_OUTAGE"]) if polarity == "yes" \
            else ([], ["APP_ERROR"])

    if "colleagues" in q and "same function" in q and "error" in q:
        return (["APP_ERROR", "APP_OUTAGE"], []) if polarity == "yes" \
            else ([], ["APP_ERROR"])

    # ------------------------------------------------------------------
    # Sync rules
    # ------------------------------------------------------------------
    if "all records delayed or only specific records" in q:
        # "only specific records" → yes means partial, more likely SYNC_DELAY
        return (["SYNC_DELAY"], []) if polarity == "yes" \
            else ([], ["SYNC_DELAY"])

    if "source system" in q and "destination" in q and "stale" in q:
        return (["SYNC_DELAY"], ["APP_OUTAGE"]) if polarity == "yes" \
            else ([], ["SYNC_DELAY"])

    # ------------------------------------------------------------------
    # VPN rules
    # ------------------------------------------------------------------
    if "colleagues at the same site connect to vpn" in q:
        # Yes = others connect fine → individual VPN client issue
        return (["VPN_CLIENT_ISSUE"], ["VPN_OUTAGE"]) if polarity == "yes" \
            else (["VPN_OUTAGE"], ["VPN_CLIENT_ISSUE"])

    if "vpn client show a local configuration" in q:
        return (["VPN_CLIENT_ISSUE"], []) if polarity == "yes" \
            else ([], ["VPN_CLIENT_ISSUE"])

    if "multiple users" in q and "same site" in q and "vpn" in q:
        return (["VPN_OUTAGE"], ["VPN_CLIENT_ISSUE"]) if polarity == "yes" \
            else ([], ["VPN_OUTAGE"])

    if "vpn health" in q and "unavailable" in q:
        return (["VPN_OUTAGE"], []) if polarity == "yes" \
            else ([], ["VPN_OUTAGE"])

    # ------------------------------------------------------------------
    # Wi-Fi / DNS rules
    # ------------------------------------------------------------------
    if "another device connect to the same wi-fi" in q:
        return ([], ["WIFI_FAILURE"]) if polarity == "yes" \
            else (["WIFI_FAILURE"], [])

    if "internal hostnames fail" in q and "direct ip" in q:
        return (["DNS_FAILURE"], []) if polarity == "yes" \
            else ([], ["DNS_FAILURE"])

    if "external websites resolve normally" in q:
        return (["DNS_FAILURE"], []) if polarity == "yes" \
            else ([], ["DNS_FAILURE"])

    # ------------------------------------------------------------------
    # Endpoint / printer / disk rules
    # ------------------------------------------------------------------
    if "same task work on another device" in q or "colleague" in q and "device" in q:
        return (["LOCAL_ENDPOINT"], ["APP_OUTAGE"]) if polarity == "yes" \
            else ([], ["LOCAL_ENDPOINT"])

    if "one user affected or everyone using the same printer" in q:
        return (["PRINTER_OFFLINE"], ["SERVER_FAILURE"]) if polarity == "yes" \
            else (["SERVER_FAILURE"], ["PRINTER_OFFLINE"])

    if "storage warning" in q and "one device" in q:
        return (["DISK_FULL"], ["STORAGE_FAILURE"]) if polarity == "yes" \
            else (["STORAGE_FAILURE"], ["DISK_FULL"])

    # ------------------------------------------------------------------
    # Server / infrastructure rules
    # ------------------------------------------------------------------
    if "multiple users or services affected" in q and "server" in q:
        return (["SERVER_FAILURE", "APP_OUTAGE"], []) if polarity == "yes" \
            else ([], ["SERVER_FAILURE"])

    if "infrastructure health" in q and "unavailable" in q:
        return (["SERVER_FAILURE"], []) if polarity == "yes" \
            else ([], ["SERVER_FAILURE"])

    if "shared drive" in q or "shared storage" in q or "multiple users" in q and "storage" in q:
        return (["STORAGE_FAILURE"], ["DISK_FULL"]) if polarity == "yes" \
            else ([], ["STORAGE_FAILURE"])

    if "expired certificate" in q or "certificate warning" in q:
        return (["CERT_EXPIRED"], []) if polarity == "yes" \
            else ([], ["CERT_EXPIRED"])

    # ------------------------------------------------------------------
    # Security rules
    # ------------------------------------------------------------------
    if "click the link" in q or "open the attachment" in q or "enter" in q and "credentials" in q:
        return (["PHISHING"], []) if polarity == "yes" \
            else ([], ["PHISHING"])

    if "approved security tool" in q and "alert" in q:
        return (["MALWARE"], []) if polarity == "yes" \
            else ([], ["MALWARE"])

    if "files being encrypted" in q or "security tools disabled" in q:
        return (["MALWARE"], []) if polarity == "yes" \
            else ([], ["MALWARE"])

    # ------------------------------------------------------------------
    # Request for guidance rules
    # ------------------------------------------------------------------
    if "asking for setup instructions" in q or "asking for instructions" in q:
        # Yes = just guidance
        return (["REQUEST_GUIDANCE"], []) if polarity == "yes" \
            else ([], ["REQUEST_GUIDANCE"])

    return [], []


# ---------------------------------------------------------------------------
# Answer submission
# ---------------------------------------------------------------------------

def submit_answer(
    state: DiagnosticState,
    answer: str,
    evidence_id: str,
    *,
    question: str | None = None,
) -> DiagnosticState:
    """Record an answer to the outstanding question and advance the investigation.

    Interpret explicit answers and narrowly scoped reported observations.
    Preserve ambiguous text without inventing tool evidence or confirmation.
    """
    if state.status in {"diagnosed", "escalated", "resolved", "closed"}:
        raise ValueError(f"Cannot submit an answer when investigation status is {state.status!r}")
    outstanding = state.next_question
    chosen_question = question or outstanding
    if not outstanding:
        raise ValueError("There is no outstanding diagnostic question")
    if chosen_question != outstanding:
        raise ValueError("Answer must correspond to the current outstanding question")
    if chosen_question not in state.questions_asked:
        raise ValueError("The supplied question was not asked in this investigation")

    supports, contradicts = _map_answer_to_diagnoses(chosen_question, answer)
    interpreted = interpret_answer(chosen_question, answer)
    if interpreted:
        state.ticket.metadata.setdefault('interpreted_answers', {})[evidence_id] = {
            'question': chosen_question, 'facts': interpreted['facts']}
    state.ticket.metadata.pop('clarification_question', None)
    evidence = Evidence(
        evidence_id=evidence_id,
        description=f"User answered the diagnostic question: {chosen_question}",
        value=answer,
        source="user_answer",
        supports=supports,
        contradicts=contradicts,
    )
    _introduce_reported_hypotheses(state, evidence, interpreted)
    if _reported_credential_exposure(answer) or (interpreted and interpreted['facts'].get('security_notice') == 'REPORTED'):
        state.ticket.metadata.setdefault('reported_security_evidence_ids', []).append(evidence_id)
    _add_trace(
        state,
        event_type="answer_received",
        description=f"Recorded an answer to: {chosen_question}",
        rationale=(
            "Only explicit, narrowly scoped reported facts are mapped to candidates. "
            "The answer is not sufficient on its own to confirm a diagnosis."
        ),
        candidate_ids=supports + contradicts,
    )
    question_count = len(state.questions_asked)
    add_evidence(state, evidence)
    if (question_family(chosen_question) not in {None, 'application_scope', 'error_detail', 'sign_in_detail'}
            and interpreted is None and not uncertain(answer)
            and not _requires_human_escalation(state.ticket) and not state.final_diagnosis):
        attempts = state.ticket.metadata.setdefault('answer_clarifications', {})
        if not attempts.get(chosen_question):
            attempts[chosen_question] = 1
            # The provisional next question was never shown: do not mark it asked.
            state.questions_asked = state.questions_asked[:question_count]
            state.ticket.metadata['clarification_question'] = chosen_question
            state.next_question = chosen_question
            state.status = 'in_progress'
            state.recommended_action = 'investigate'
            state.rationale = 'The answer did not identify a clear observation or option. Clarify once without assuming yes or no.'
    return state


def _introduce_reported_hypotheses(state, evidence, interpreted):
    """Extend the shortlist from observed facts, retaining contradictory evidence."""
    if not interpreted or state.ticket.metadata.get('pending_correction_review'):
        return
    taxonomy = {r['diagnosis_code']: r for r in json.loads(
        (_KNOWLEDGE_DIR / 'taxonomy.json').read_text(encoding='utf-8'))}
    active = {c.diagnosis_id for c in state.candidates}
    new_codes = set(evidence.supports) & set(taxonomy) - active
    for code in sorted(new_codes):
        row = taxonomy[code]
        reopened = any(c['diagnosis_id'] == code for c in state.eliminated_diagnoses)
        candidate = DiagnosisCandidate(code, row.get('label', code),
            row.get('domain', 'Other'), row.get('category', 'Unclassified'),
            row.get('resolver_group_id', 'GRP-L1'), required_evidence=['Confirm with applicable knowledge and current observations.'])
        candidate.supporting_evidence_ids = [e.evidence_id for e in state.evidence if code in e.supports]
        candidate.contradicting_evidence_ids = [e.evidence_id for e in state.evidence if code in e.contradicts]
        state.candidates.append(candidate)
        state.archived_candidates = [c for c in state.archived_candidates if c.diagnosis_id != code]
        state.eliminated_diagnoses = [c for c in state.eliminated_diagnoses if c['diagnosis_id'] != code]
        _add_trace(state, event_type='hypothesis_reopened' if reopened else 'hypothesis_introduced',
            description=f'New reported observations introduce {code}.',
            rationale='Unconfirmed hypothesis: retain prior observations and run supported checks before concluding.',
            evidence_ids=[evidence.evidence_id], candidate_ids=[code])
    if new_codes:
        state.candidates = [c for c in state.candidates if c.diagnosis_id not in {'UNKNOWN_CAUSE', 'UNKNOWN_ISSUE'}]
        state.ticket.metadata['knowledge_refresh_required'] = True


def record_correction_for_review(state, text, evidence_id):
    """Retain a post-handoff correction without inferring a new diagnosis."""
    if state.status in {'resolved', 'closed'}:
        raise ValueError('Resolved or closed investigations cannot be changed.')
    if any(e.evidence_id == evidence_id for e in state.evidence):
        raise ValueError('Duplicate evidence ID.')
    previous = state.final_diagnosis
    state.evidence.append(Evidence(evidence_id, 'User provided a correction after handoff',
        text, 'user_answer'))
    state.final_diagnosis, state.confidence = None, None
    state.status, state.recommended_action, state.next_question = 'escalated', 'escalate', None
    state.ticket.metadata.pop('diagnosis_basis', None)
    state.ticket.metadata['pending_correction_review'] = {
        'evidence_id': evidence_id, 'previous_diagnosis': previous}
    for candidate in state.candidates:
        if candidate.status == 'confirmed':
            candidate.status = 'plausible'
    state.rationale = 'A new factual correction may invalidate the earlier conclusion. Supervisor review is required before further action.'
    _add_trace(state, event_type='correction_received', description=text,
        rationale=state.rationale, evidence_ids=[evidence_id], candidate_ids=[])


def reinterpret_saved_answers(state):
    """Repair unmapped legacy answers using their original question and evidence ID."""
    for evidence in state.evidence:
        prefix = 'User answered the diagnostic question: '
        if (evidence.source != 'user_answer'
                or not evidence.description.startswith(prefix) or not isinstance(evidence.value, str)):
            continue
        question = evidence.description[len(prefix):]
        interpreted = interpret_answer(question, evidence.value)
        entries = state.ticket.metadata.setdefault('interpreted_answers', {})
        prior = entries.get(evidence.evidence_id)
        if not interpreted and not prior:
            continue
        if prior and interpreted and prior.get('facts') == interpreted['facts']:
            continue
        if prior:
            # Remove stale parser conclusions using the same original source ID.
            for candidate in state.candidates + state.archived_candidates:
                candidate.supporting_evidence_ids = [x for x in candidate.supporting_evidence_ids if x != evidence.evidence_id]
                candidate.contradicting_evidence_ids = [x for x in candidate.contradicting_evidence_ids if x != evidence.evidence_id]
            entries.pop(evidence.evidence_id, None)
            old_contradictions = set(evidence.contradicts)
            evidence.supports, evidence.contradicts = [], []
            for candidate in list(state.archived_candidates):
                if candidate.diagnosis_id in old_contradictions and not candidate.contradicting_evidence_ids:
                    candidate.status, candidate.elimination_reason = 'plausible', None
                    if not any(c.diagnosis_id == candidate.diagnosis_id for c in state.candidates):
                        state.candidates.append(candidate)
                    state.archived_candidates.remove(candidate)
                    state.eliminated_diagnoses = [e for e in state.eliminated_diagnoses if e['diagnosis_id'] != candidate.diagnosis_id]
            if state.final_diagnosis:
                state.final_diagnosis, state.confidence = None, None
                state.status, state.recommended_action, state.next_question = 'in_progress', 'investigate', None
                state.ticket.metadata.pop('diagnosis_basis', None)
        if not interpreted:
            _add_trace(state, event_type='answer_interpretation_repaired',
                description='Removed an unsupported prior interpretation; the original user observation is retained.',
                rationale='Ambiguous or self-correcting text cannot authorize a diagnosis.', evidence_ids=[evidence.evidence_id])
            continue
        if (question_family(question) == 'wifi_peer' and 'WIFI_FAILURE' in evidence.contradicts
                and interpreted['facts'].get('peer_wifi_connection') == 'WORKS'):
            evidence.contradicts.remove('WIFI_FAILURE')
            for candidate in state.candidates + state.archived_candidates:
                candidate.contradicting_evidence_ids = [x for x in candidate.contradicting_evidence_ids if x != evidence.evidence_id]
            archived = next((c for c in state.archived_candidates if c.diagnosis_id == 'WIFI_FAILURE'), None)
            if archived and not archived.contradicting_evidence_ids:
                archived = deepcopy(archived)
                archived.status, archived.elimination_reason = 'plausible', None
                if not any(c.diagnosis_id == 'WIFI_FAILURE' for c in state.candidates):
                    state.candidates.append(archived)
                state.eliminated_diagnoses = [x for x in state.eliminated_diagnoses if x['diagnosis_id'] != 'WIFI_FAILURE']
        entries[evidence.evidence_id] = {'question': question, 'facts': interpreted['facts']}
        evidence.supports = interpreted['supports']
        evidence.contradicts = interpreted['contradicts']
        for candidate in state.candidates:
            if candidate.diagnosis_id in evidence.supports and evidence.evidence_id not in candidate.supporting_evidence_ids:
                candidate.supporting_evidence_ids.append(evidence.evidence_id)
            if candidate.diagnosis_id in evidence.contradicts and evidence.evidence_id not in candidate.contradicting_evidence_ids:
                candidate.contradicting_evidence_ids.append(evidence.evidence_id)
        _add_trace(state, event_type='answer_interpretation_repaired',
            description='Interpreted a previously unmapped user observation using its original evidence ID.',
            rationale='This remains USER_RESPONSE evidence; no tool check or user answer was fabricated.',
            evidence_ids=[evidence.evidence_id], candidate_ids=evidence.supports + evidence.contradicts)


def reassess_review_state(state):
    """Resume a legacy exhausted investigation without inventing new evidence."""
    if (not state.ticket.metadata.get('diagnostic_review_mode') or _requires_human_escalation(state.ticket)
            or state.ticket.metadata.get('pending_correction_review')):
        return
    if state.status in {'resolved', 'closed', 'diagnosed'}:
        return
    if state.status == 'escalated':
        answered = {e.description.removeprefix('User answered the diagnostic question: ')
            for e in state.evidence if e.source == 'user_answer'}
        # v5 marked provisional questions as asked before backend checks changed
        # the visible question. Keep actual answered questions when recovering.
        state.questions_asked = [q for q in state.questions_asked if q in answered]
    if _try_confirm_diagnosis(state):
        return
    _check_outage_signal(state)
    if any(c.diagnosis_id in _OUTAGE_CANDIDATE_IDS for c in state.candidates):
        return
    question = choose_next_question(state)
    if question and not state.next_question:
        state.status, state.recommended_action = 'in_progress', 'investigate'
        state.next_question = question
        state.questions_asked.append(question)


# ---------------------------------------------------------------------------
# Evidence recording
# ---------------------------------------------------------------------------

def reconcile_supported_hypotheses(state: DiagnosticState) -> None:
    """Reopen an excluded hypothesis when current evidence supports it.

    Conflicting observations are retained. Reopening never confirms a diagnosis
    or authorizes resolution, and works for legacy snapshots without archives.
    """
    active = {c.diagnosis_id for c in state.candidates}
    for excluded in list(state.eliminated_diagnoses):
        code = excluded['diagnosis_id']
        supporting = [e.evidence_id for e in state.evidence if code in e.supports
            and e.source in {'user_answer', 'diagnostic_check'}]
        if code in active or not supporting:
            continue
        archived = next((c for c in state.archived_candidates if c.diagnosis_id == code), None)
        if archived is None:
            archived = next((c for c in _initial_candidates(state.ticket) if c.diagnosis_id == code), None)
        if archived is None:
            past = next((m for m in state.historical_matches if m.get('diagnosis_code') == code), {})
            archived = DiagnosisCandidate(code, code.replace('_', ' ').title(),
                state.ticket.domain or 'Other', state.ticket.category or 'Unclassified',
                past.get('owner_group_id') or 'Service Desk L1',
                required_evidence=['Resolve conflicting current observations before confirming this diagnosis.'])
        candidate = deepcopy(archived)
        candidate.status = 'plausible'
        candidate.elimination_reason = None
        candidate.supporting_evidence_ids = supporting
        candidate.contradicting_evidence_ids = [e.evidence_id for e in state.evidence if code in e.contradicts]
        state.candidates.append(candidate)
        state.eliminated_diagnoses = [e for e in state.eliminated_diagnoses if e['diagnosis_id'] != code]
        state.archived_candidates = [c for c in state.archived_candidates if c.diagnosis_id != code]
        active.add(code)
        _add_trace(state, event_type='hypothesis_reopened',
            description=f'Reopened {code} because current evidence conflicts with its previous exclusion.',
            rationale='Keep both supporting and contradicting observations; this is an unconfirmed hypothesis.',
            evidence_ids=candidate.supporting_evidence_ids + candidate.contradicting_evidence_ids,
            candidate_ids=[code])

    # Legacy snapshots may never have shortlisted the shared-service cause.
    # Introduce only canonical shared hypotheses backed by actual observations;
    # retrieval matches and ticket keywords alone do not authorize this step.
    new_codes = {code for e in state.evidence
        if e.source in {'user_answer', 'diagnostic_check'}
        for code in e.supports if code in _OUTAGE_CANDIDATE_IDS} - active
    if not new_codes:
        return
    taxonomy = {row['diagnosis_code']: row for row in json.loads(
        (_KNOWLEDGE_DIR / 'taxonomy.json').read_text(encoding='utf-8'))}
    for code in sorted(new_codes & taxonomy.keys()):
        row = taxonomy[code]
        candidate = DiagnosisCandidate(code, row['label'], row['domain'], row['category'],
            row['resolver_group_id'], required_evidence=[
                'Supervisor must screen current service health and related tickets for this CI/location.'])
        candidate.supporting_evidence_ids = [e.evidence_id for e in state.evidence
            if code in e.supports and e.source in {'user_answer', 'diagnostic_check'}]
        candidate.contradicting_evidence_ids = [e.evidence_id for e in state.evidence if code in e.contradicts]
        state.candidates.append(candidate)
        state.archived_candidates = [c for c in state.archived_candidates if c.diagnosis_id != code]
        _add_trace(state, event_type='hypothesis_introduced',
            description=f'Added {code} because current observations introduce a shared-service possibility.',
            rationale='Preserve both supporting and contradictory evidence. This is a screening hypothesis, not a confirmed outage.',
            evidence_ids=candidate.supporting_evidence_ids + candidate.contradicting_evidence_ids,
            candidate_ids=[code])


def add_evidence(
    state: DiagnosticState,
    evidence: Evidence,
) -> DiagnosticState:
    """Record new evidence and update candidate support."""
    if any(item.evidence_id == evidence.evidence_id for item in state.evidence):
        raise ValueError(f"Duplicate evidence_id: {evidence.evidence_id}")
    state.evidence.append(evidence)
    reconcile_supported_hypotheses(state)

    for candidate in state.candidates:
        if candidate.diagnosis_id in evidence.supports:
            if evidence.evidence_id not in candidate.supporting_evidence_ids:
                candidate.supporting_evidence_ids.append(evidence.evidence_id)

        if candidate.diagnosis_id in evidence.contradicts:
            if evidence.evidence_id not in candidate.contradicting_evidence_ids:
                candidate.contradicting_evidence_ids.append(evidence.evidence_id)
            if candidate.supporting_evidence_ids:
                # A contradiction to supported evidence requires reconciliation,
                # rather than silently removing the hypothesis and its support.
                candidate.status = 'plausible'
                candidate.elimination_reason = None
                _add_trace(state, event_type='evidence_conflict_detected',
                    description=f'Conflicting observations for {candidate.diagnosis_id}.',
                    rationale='Retain both observations and require further investigation or human review.',
                    evidence_ids=candidate.supporting_evidence_ids + candidate.contradicting_evidence_ids,
                    candidate_ids=[candidate.diagnosis_id])
                continue
            candidate.status = "eliminated"
            candidate.elimination_reason = evidence.description
            state.archived_candidates = [c for c in state.archived_candidates if c.diagnosis_id != candidate.diagnosis_id]
            state.archived_candidates.append(deepcopy(candidate))
            state.eliminated_diagnoses.append(
                {
                    "diagnosis_id": candidate.diagnosis_id,
                    "reason": evidence.description,
                }
            )

    _add_trace(
        state,
        event_type="evidence_added",
        description=evidence.description,
        rationale=f"Evidence source: {evidence.source}.",
        evidence_ids=[evidence.evidence_id],
        candidate_ids=evidence.supports + evidence.contradicts,
    )

    state.candidates = [
        c for c in state.candidates if c.status != "eliminated"
    ]
    if state.final_diagnosis:
        confirmed = next((c for c in state.candidates if c.diagnosis_id == state.final_diagnosis), None)
        pattern_invalidated = (state.ticket.metadata.get('diagnosis_basis') == 'REPORTED_DIAGNOSTIC_PATTERN'
            and not reported_pattern(state, state.final_diagnosis))
        if confirmed is None or confirmed.contradicting_evidence_ids or pattern_invalidated:
            previous = state.final_diagnosis
            state.final_diagnosis = None
            state.confidence = None
            state.status = 'in_progress'
            state.recommended_action = 'investigate'
            _add_trace(state, event_type='diagnosis_reopened',
                description=f'New contradictory evidence invalidates the previous conclusion {previous}.',
                rationale='A conflicting diagnosis cannot authorize routing or resolution as an established conclusion.',
                evidence_ids=[evidence.evidence_id], candidate_ids=[previous])

    # Mandatory escalation always takes precedence.
    if _requires_human_escalation(state.ticket):
        state.recommended_action = "escalate"
        state.status = "escalated"
        state.next_question = None
        state.rationale = (
            "Mandatory human escalation applies; evidence collection "
            "does not override this requirement."
        )
        return state

    if _try_confirm_diagnosis(state):
        return state

    # Step 7: re-check outage signal after new evidence is added.
    _check_outage_signal(state)
    if state.status == "escalated":
        return state

    state.next_question = choose_next_question(state)
    if state.next_question:
        state.questions_asked.append(state.next_question)

    if state.next_question:
        state.recommended_action = "investigate"
        state.status = "in_progress"
        state.rationale = (
            "More evidence is needed. No diagnosis is confirmed by this step."
        )
    else:
        state.recommended_action = "escalate"
        state.status = "escalated"
        state.rationale = (
            "No unused targeted question remains. Human investigation "
            "is needed rather than forcing a diagnosis."
        )
        findings = diagnostic_findings(state)
        if findings.get('observations'):
            state.rationale = ('Reported observations: ' + ' '.join(o['description'] for o in findings['observations'])
                + ' ' + ' '.join(findings['verification_gaps'])
                + ' No diagnosis is confirmed. Recommend human review; no repair or assignment was executed.')
        _add_trace(
            state,
            event_type="escalation_required",
            description="The current diagnostic rules need human follow-up.",
            rationale=state.rationale,
        )

    return state


# ---------------------------------------------------------------------------
# Step 5: Resolution walk-through
# ---------------------------------------------------------------------------

def start_resolution(
    state: DiagnosticState,
    articles_path: str | Path = _DEFAULT_ARTICLES_FILE,
) -> dict:
    """Return the ordered self-service/L1 resolution steps for the confirmed diagnosis.

    Requirements:
    - Diagnosis must be confirmed (status == 'diagnosed').
    - The matching knowledge article must be approved and agent_resolvable == True.
    - No SPECIALIST steps may exist in the article (those require human action).
    Returns a dict with 'steps', 'article_id', and 'resolution_conditions' on
    success, or raises ValueError describing the unmet condition.
    """
    if state.status != "diagnosed":
        raise ValueError(
            f"Resolution can only begin when status is 'diagnosed'; "
            f"current status is '{state.status}'."
        )
    if not state.final_diagnosis:
        raise ValueError("No confirmed diagnosis is set on this state.")

    # Find the confirmed candidate
    confirmed = next(
        (c for c in state.candidates if c.diagnosis_id == state.final_diagnosis
         and c.status == "confirmed"),
        None,
    )
    if confirmed is None:
        raise ValueError(
            f"Confirmed candidate for {state.final_diagnosis} not found."
        )

    article_id = confirmed.knowledge_article_id
    if not article_id:
        raise ValueError(
            f"No approved knowledge article is linked to {state.final_diagnosis}."
        )

    article = get_article_by_id(article_id, path=articles_path)
    if article is None:
        raise ValueError(
            f"Article {article_id} is not found or not approved."
        )

    guidance = get_resolution_guidance(article)
    restrictions = guidance.get('mandatory_human_escalation') or []
    recognized = {'security_sensitive', 'privileged_access', 'reported_priority=1', 'insufficient evidence'}
    if any(rule not in recognized for rule in restrictions):
        raise ValueError('Article has human restrictions requiring review before automated resolution.')
    if state.ticket.metadata.get('pending_correction_review'):
        raise ValueError('A factual correction requires Supervisor review.')

    if not guidance.get("resolvable_by_agent"):
        raise ValueError(
            f"Article {article_id} is not marked as agent_resolvable. "
            "Human specialist action is required."
        )

    if _requires_human_escalation(state.ticket):
        raise ValueError('Mandatory human handling prohibits automated resolution.')

    steps = guidance.get("resolution_steps", [])
    if any(isinstance(s, dict) and s.get('level') == 'SPECIALIST' for s in steps):
        raise ValueError('Article includes specialist steps; human support is required.')
    tool_names = {
        'check_account_status': {'enabled', 'locked', 'password_expired', 'mfa_enrolled', 'mfa_locked'},
        'check_application_entitlement': {'entitled', 'provisioning_state'},
        'check_service_health': {'state', 'scope'},
    }
    if not guidance.get('resolution_conditions'):
        raise ValueError('Article has no machine-verifiable resolution conditions.')
    for condition in guidance.get('resolution_conditions', []):
        if not isinstance(condition, dict) or condition.get('field') not in tool_names.get(condition.get('tool'), set()):
            raise ValueError('Resolution condition cannot be verified by the agent.')
        observations = [e.value for e in state.evidence if e.source == 'diagnostic_check'
                        and isinstance(e.value, dict)
                        and tool_names[condition['tool']].intersection(e.value)]
        if not observations or str(observations[-1].get(condition['field'], '')).upper() != str(condition.get('equals')).upper():
            raise ValueError('Required resolution condition is not met: ' + condition['field'])
    # Filter to only SELF_SERVICE and L1 steps — SPECIALIST steps must not be
    # presented to the user as something the agent can do.
    agent_steps = [
        s for s in steps
        if isinstance(s, dict) and s.get("level") in {"SELF_SERVICE", "L1"}
    ]
    if not agent_steps:
        raise ValueError(
            f"Article {article_id} has no SELF_SERVICE or L1 steps available "
            "for agent-guided resolution."
        )

    _add_trace(
        state,
        event_type="resolution_started",
        description=(
            f"Resolution walk-through started for {state.final_diagnosis} "
            f"using article {article_id}."
        ),
        rationale=(
            "Article is approved and agent_resolvable=True. "
            "No SPECIALIST steps are presented."
        ),
        candidate_ids=[state.final_diagnosis],
    )

    return {
        "article_id": article_id,
        "diagnosis_code": state.final_diagnosis,
        "steps": agent_steps,
        "resolution_conditions": guidance.get("resolution_conditions", []),
    }


def confirm_resolution(
    state: DiagnosticState,
    confirmed_by_user: bool,
    completed_step_ids: list[str],
) -> DiagnosticState:
    """Mark the ticket resolved after the user confirms the fix worked.

    Sets state.status = 'resolved' only when confirmed_by_user is True and at
    least one step_id is recorded.  Otherwise leaves the state in 'diagnosed'
    for further investigation or human handoff.
    """
    if state.status != "diagnosed":
        raise ValueError(
            f"confirm_resolution requires status 'diagnosed'; got '{state.status}'."
        )

    if not confirmed_by_user:
        state.rationale = (
            "User did not confirm the fix worked. Resolution is not recorded. "
            "Continue investigation or escalate to human support."
        )
        _add_trace(
            state,
            event_type="resolution_unconfirmed",
            description="User did not confirm resolution success.",
            rationale=state.rationale,
            candidate_ids=[state.final_diagnosis] if state.final_diagnosis else [],
        )
        return state

    if not completed_step_ids:
        raise ValueError("At least one completed_step_id must be provided.")

    state.status = "resolved"
    state.recommended_action = "resolved"
    state.rationale = (
        f"User confirmed the issue is fixed after completing steps: "
        f"{', '.join(completed_step_ids)}. "
        f"Diagnosis: {state.final_diagnosis}."
    )
    _add_trace(
        state,
        event_type="resolution_confirmed",
        description="User confirmed the fix succeeded; ticket marked resolved.",
        rationale=state.rationale,
        candidate_ids=[state.final_diagnosis] if state.final_diagnosis else [],
    )
    return state


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------

def build_result(state: DiagnosticState) -> DiagnosticResult:
    """Convert the current state into the public result structure."""
    return DiagnosticResult(
        ticket_id=state.ticket.ticket_id,
        diagnosis=state.final_diagnosis,
        evidence=state.evidence,
        confidence=state.confidence,
        recommended_action=state.recommended_action,
        rationale=state.rationale or (
            "Investigation is incomplete; no confirmed diagnosis is available."
        ),
        next_question=state.next_question,
        remaining_candidates=state.candidates,
        eliminated_diagnoses=state.eliminated_diagnoses,
        trace=state.trace,
        status=state.status,
        knowledge_article_id=next(
            (
                c.knowledge_article_id
                for c in state.candidates
                if c.knowledge_article_id
            ),
            None,
        ),
        knowledge_matches=state.knowledge_matches,
        historical_matches=state.historical_matches,
        candidate_rankings=rank_candidates(state),
    )

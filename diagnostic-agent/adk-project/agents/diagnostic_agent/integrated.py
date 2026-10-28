"""Backend-connected diagnostic investigation entry point.

This module wires the deterministic engine (engine.py) to the live backend.
It implements the full multi-turn diagnostic loop described in the requirements:

  Symptoms → Candidate Diagnoses → Diagnostic Questions → Evidence
  → Eliminate Alternatives → Diagnosis → Resolve / Route / Escalate

The first call to investigate_ticket() runs the initial investigation and
returns either:
  - ASK_MORE  — a next_question is ready; the caller must collect the user's
                answer and call submit_answer_and_continue().
  - ESCALATE  — mandatory escalation (security/privileged/P1) or outage
                signal; the Supervisor handles routing.
  - ROUTE     — diagnosis confirmed; the Supervisor assigns to a resolver group.
  - RESOLVE   — agent-resolvable diagnosis confirmed; walk-through steps
                returned; call confirm_resolution_and_close() after user confirms.

Step 6: every decision writes a worklog entry (QUESTION, EVIDENCE, DIAGNOSIS, NOTE).
Step 7: outage detection calls count_recent_tickets + find_open_global_tickets
        when shared-service candidates are present.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .backend_client import DiagnosticBackendClient, BackendRequestError
from .engine import (
    start_investigation,
    submit_answer,
    add_evidence,
    build_result,
    start_resolution,
    confirm_resolution,
    _requires_human_escalation,
    _OUTAGE_CANDIDATE_IDS,
    _DEFAULT_ARTICLES_FILE,
    _DEFAULT_HISTORY_FILE,
    _check_outage_signal,
    choose_next_question,
    reconcile_supported_hypotheses,
    reinterpret_saved_answers,
    record_correction_for_review,
    reassess_review_state,
)
from .answers import diagnostic_findings
from .models import Evidence, TicketInput
from .session_store import JsonSessionStore
from .llm import redact_secrets

_CANONICAL_CODES = frozenset(row['diagnosis_code'] for row in json.loads(
    (_DEFAULT_ARTICLES_FILE.parent / 'taxonomy.json').read_text(encoding='utf-8')))

def _align_backend_codes(state: Any) -> None:
    """Keep internal legacy aliases out of the backend's canonical contract."""
    state.candidates = [c for c in state.candidates if c.diagnosis_id in _CANONICAL_CODES]
    state.archived_candidates = [c for c in state.archived_candidates if c.diagnosis_id in _CANONICAL_CODES]
    state.eliminated_diagnoses = [e for e in state.eliminated_diagnoses if e['diagnosis_id'] in _CANONICAL_CODES]
    if state.final_diagnosis and state.final_diagnosis not in _CANONICAL_CODES:
        state.final_diagnosis = None
        state.confidence = None
        state.status = 'escalated'
        state.next_question = None
        state.recommended_action = 'escalate'
        state.rationale = 'Only an internal legacy hypothesis was supported; a canonical diagnosis requires human review.'


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _action(prefix: str) -> str:
    return f"diag-{prefix}-{uuid.uuid4().hex[:20]}"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get(d: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if d.get(key) is not None:
            return d[key]
    return None


def _ticket_to_input(ticket: dict[str, Any]) -> TicketInput:
    """Convert a raw backend ticket record to a TicketInput."""
    priority = str(ticket.get("reported_priority", ticket.get("priority", "3")))
    return TicketInput(
        ticket_id=str(ticket.get("ticket_id", "")),
        summary=str(ticket.get("summary", "")),
        description=str(ticket.get("description", "")),
        priority=priority,
        ticket_class=str(ticket.get("ticket_class", "INCIDENT")),
        impact=ticket.get("impact"),
        urgency=ticket.get("urgency"),
        language=ticket.get("language"),
        domain=ticket.get("domain"),
        category=ticket.get("category"),
        subcategory=ticket.get("subcategory"),
        severity=ticket.get("severity"),
        asset_id=ticket.get("asset_id"),
        configuration_item_id=ticket.get("configuration_item_id"),
        location_id=ticket.get("location_id"),
        security_sensitive=bool(ticket.get("security_sensitive")),
        privileged_access=bool(ticket.get("privileged_access")),
    )


def _confidence_from_state(state: Any) -> str:
    """Grade observable evidence, never an LLM's self-reported probability."""
    if state.status not in {'diagnosed', 'resolved'} or not state.final_diagnosis:
        return "LOW"
    if state.ticket.metadata.get('diagnosis_basis') == 'REPORTED_DIAGNOSTIC_PATTERN':
        return 'MEDIUM'
    # A directly confirmed, unlocked/enabled account with an expired password
    # and consistent user evidence does not need a majority vote from history.
    if state.final_diagnosis == 'PASSWORD_EXPIRED':
        facts = [e.value for e in state.evidence if e.source == 'diagnostic_check' and isinstance(e.value, dict)
            and 'password_expired' in e.value]
        confirming = {'password_expired': 'TRUE', 'enabled': 'TRUE', 'locked': 'FALSE', 'mfa_locked': 'FALSE'}
        candidate = next((c for c in state.candidates if c.diagnosis_id == 'PASSWORD_EXPIRED'), None)
        guidance = any(m.get('diagnosis_code') == 'PASSWORD_EXPIRED' and m.get('approved') is True for m in state.knowledge_matches)
        corroboration = any(e.source == 'user_answer' and 'PASSWORD_EXPIRED' in e.supports for e in state.evidence)
        if (facts and all(str(facts[-1].get(k)).upper() == v for k, v in confirming.items())
                and candidate and not candidate.contradicting_evidence_ids and guidance and corroboration
                and not _requires_human_escalation(state.ticket) and not state.ticket.metadata.get('pending_correction_review')):
            return 'HIGH'
    # Other implemented direct-state diagnoses have their own evidence rule.
    # A lexical score or historical majority cannot raise confidence by itself.
    from .answers import collected_facts
    observed = collected_facts(state)
    candidate = next((c for c in state.candidates if c.diagnosis_id == state.final_diagnosis), None)
    applicable = any(m.get('diagnosis_code') == state.final_diagnosis and m.get('approved') is True
        for m in state.knowledge_matches)
    checks = [e.value for e in state.evidence if e.source == 'diagnostic_check' and isinstance(e.value, dict)]
    locked = any(str(v.get('locked')).upper() == 'TRUE' and str(v.get('enabled')).upper() == 'TRUE'
        and str(v.get('password_expired')).upper() == 'FALSE' for v in checks)
    absent = any(str(v.get('entitled')).upper() == 'FALSE' and str(v.get('provisioning_state')).upper() == 'ABSENT'
        for v in checks)
    if candidate and not candidate.contradicting_evidence_ids and applicable:
        if state.final_diagnosis == 'ACCOUNT_LOCKED' and locked and observed.get('account_message') == 'LOCKED':
            return 'HIGH'  # Current lock state, not the unexposed security-policy cause.
        if state.final_diagnosis == 'MISSING_ENTITLEMENT' and absent and observed.get('other_application_access') == 'WORKS':
            return 'HIGH'
    return "MEDIUM"


# ---------------------------------------------------------------------------
# Step 6: Worklog helpers — write a worklog entry, swallow backend errors
# so they never abort the diagnostic flow.
# ---------------------------------------------------------------------------

def _worklog(
    client: DiagnosticBackendClient,
    ticket_id: str,
    entry_type: str,
    summary: str,
    *,
    rationale: str = "",
    evidence_ids: list[str] | None = None,
    knowledge_article_ids: list[str] | None = None,
    historical_ticket_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Write one worklog entry; return the response or an error dict."""
    try:
        return client.add_worklog_entry(ticket_id, {
            "action_id": _action("wl"),
            "entry_type": entry_type,
            "summary": redact_secrets(summary),
            "rationale": redact_secrets(rationale or summary),
            "evidence_ids": evidence_ids or [],
            "knowledge_article_ids": knowledge_article_ids or [],
            "historical_ticket_ids": historical_ticket_ids or [],
        })
    except BackendRequestError:
        raise  # Required audit persistence must succeed before continuing.


# ---------------------------------------------------------------------------
# Step 7: Outage detection helpers
# ---------------------------------------------------------------------------

def _run_outage_checks(
    client: DiagnosticBackendClient,
    ticket: dict[str, Any],
    state: Any,
    result: dict[str, Any],
) -> None:
    """Check for existing global ticket and recent ticket counts.

    Mutates `result` in place to add outage detection findings.
    """
    tid = str(ticket.get("ticket_id", ""))
    ci = ticket.get("configuration_item_id")
    location = ticket.get("location_id")
    category = ticket.get("category")

    outage_candidates = [
        c.diagnosis_id for c in state.candidates
        if c.diagnosis_id in _OUTAGE_CANDIDATE_IDS
    ]
    if not outage_candidates:
        return

    # 1. Check for an existing open global ticket.
    global_search: dict[str, Any] = {}
    if ci or category:
        try:
            global_search = _as_dict(client.find_open_global_tickets({
                "category": category,
                "configuration_item_id": ci,
                "location_id": location,
            }))
        except BackendRequestError as exc:
            global_search = {"error": str(exc)}

    # GlobalResults shape: {"results": [{ticket_id, severity, owner_group_id, ...}]}
    global_results = global_search.get("results", [])
    existing_global = global_results[0]["ticket_id"] if global_results else None
    result["outage_detection"] = {
        "outage_candidates": outage_candidates,
        "existing_global_ticket": existing_global,
        "global_search_result": global_search,
    }

    if existing_global:
        # Draft policy does not authorize linking; return the proposal to the Supervisor.
        result['outage_detection']['proposed_global_ticket_id'] = existing_global
        result['outage_detection']['human_policy_review_required'] = True
        result["outcome"] = "KNOWN_ISSUE"
        result["recommended_action"] = "ESCALATE"
        result["rationale"] = (
            f"An open global ticket ({existing_global}) already exists for "
            "this category/CI/location. Supervisor must review the proposed link "
            "under the pending policy before claiming this ticket is linked."
        )
        _worklog(
            client, tid, "NOTE",
            f"[DiagnosticAgent] Proposed link to existing global ticket {existing_global}; human review required.",
            rationale=result["rationale"],
        )
        return

    # 2. Count recent tickets to see if threshold is met for a new global.
    count_result: dict[str, Any] = {}
    if ci or category:
        try:
            count_result = _as_dict(client.count_recent_tickets({
                "category": category,
                "configuration_item_id": ci,
                "location_id": location,
                "window_minutes": 30,
            }))
        except BackendRequestError as exc:
            count_result = {"error": str(exc)}

    ticket_count = count_result.get("count", 0)
    threshold = 3  # default; matches escalation_policy.json minimum_count
    result["outage_detection"]["recent_ticket_count"] = ticket_count
    result["outage_detection"]["count_result"] = count_result

    if isinstance(ticket_count, int) and ticket_count >= threshold:
        # Threshold met — signal the Supervisor to create a global ticket.
        result["outage_detection"]["threshold_met"] = True
        result["outcome"] = "OUTAGE_THRESHOLD_MET"
        result["recommended_action"] = "ESCALATE"
        result["rationale"] = (
            f"Outage threshold met: {ticket_count} tickets with matching "
            f"category/CI/location in the last 30 minutes. "
            "Escalating to Supervisor for global ticket creation."
        )
        _worklog(
            client, tid, "NOTE",
            f"[DiagnosticAgent] Outage threshold met ({ticket_count} tickets). "
            "Escalating for global ticket creation.",
            rationale=result["rationale"],
        )
    else:
        result["outage_detection"]["threshold_met"] = False


# ---------------------------------------------------------------------------
# Diagnostic checks (read-only backend tools)
# ---------------------------------------------------------------------------

def _run_diagnostic_checks(
    client: DiagnosticBackendClient,
    ticket: dict[str, Any],
    state: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Run safe read-only checks based on active candidates.

    Returns (checks, check_errors).  Each check result is recorded as
    diagnostic_check evidence on the state so it feeds _try_confirm_diagnosis().
    """
    tid = str(ticket.get("ticket_id", ""))
    text = f"{ticket.get('summary', '')} {ticket.get('description', '')}".lower()

    checks: list[dict[str, Any]] = []
    check_errors: list[dict[str, str]] = []

    user_id = _get(ticket, "affected_person_id", "reported_by_id")
    active_ids = {c.diagnosis_id for c in state.candidates}

    # Account status check — for any authentication/access candidate.
    auth_candidates = active_ids & {
        "ACCOUNT_LOCKED", "PASSWORD_EXPIRED", "STALE_CREDENTIALS",
        "MFA_FAILURE", "ACCOUNT_DISABLED", "ACCOUNT_LOCKED_POLICY",
    }
    existing_fields = {k for e in state.evidence if e.source == 'diagnostic_check' and isinstance(e.value, dict) for k in e.value}
    attempt = state.ticket.metadata.get('account_check_attempt', {})
    if not attempt:
        # Existing v6.8.2 checkpoints can already contain the account result.
        prior = next((e.value for e in reversed(state.evidence)
            if e.source == 'diagnostic_check' and isinstance(e.value, dict)
            and e.description.startswith('Account status check:')), None)
        if prior is not None:
            missing = [field for field in ('enabled', 'locked', 'password_expired')
                       if str(prior.get(field, 'UNKNOWN')).upper() not in {'TRUE', 'FALSE'}]
            attempt = {'user_id': str(user_id), 'status': 'UNKNOWN' if missing else 'AVAILABLE',
                       'missing_fields': missing}
            state.ticket.metadata['account_check_attempt'] = attempt
    if user_id and auth_candidates and 'locked' not in existing_fields and attempt.get('user_id') != str(user_id):
        try:
            check_result = client.check_account_status({
                "ticket_id": tid,
                "user_id": str(user_id),
                "action_id": _action("acct"),
            })
            checks.append({"tool": "check_account_status", "result": check_result})
            fields = ('enabled', 'locked', 'password_expired')
            missing = [field for field in fields if str(check_result.get(field, 'UNKNOWN')).upper() not in {'TRUE', 'FALSE'}]
            state.ticket.metadata['account_check_attempt'] = {'user_id': str(user_id),
                'status': 'UNKNOWN' if missing else 'AVAILABLE', 'missing_fields': missing}
            _record_account_check_evidence(state, check_result, tid)
        except BackendRequestError as exc:
            check_errors.append({"tool": "check_account_status", "error": str(exc)})
            state.ticket.metadata['account_check_attempt'] = {'user_id': str(user_id),
                'status': 'REJECTED' if exc.status == 422 else 'UNAVAILABLE',
                'backend_status': exc.status}
    elif auth_candidates and not user_id:
        state.ticket.metadata['account_check_attempt'] = {'status': 'MISSING_IDENTIFIER'}

    # Application entitlement check.
    app_id = _get(ticket, "configuration_item_id", "asset_id")
    entitlement_candidates = active_ids & {"MISSING_ENTITLEMENT", "APP_AUTH_FAILURE"}
    if user_id and app_id and entitlement_candidates and 'entitled' not in existing_fields:
        try:
            check_result = client.check_application_entitlement({
                "ticket_id": tid,
                "user_id": str(user_id),
                "application_id": str(app_id),
                "action_id": _action("ent"),
            })
            checks.append({"tool": "check_application_entitlement", "result": check_result})
            _record_entitlement_check_evidence(state, check_result, tid, app_id)
        except BackendRequestError as exc:
            check_errors.append({"tool": "check_application_entitlement", "error": str(exc)})

    # Service health check.
    ci = ticket.get("configuration_item_id")
    service_candidates = active_ids & {
        "APPLICATION_FAILURE", "APP_OUTAGE", "VPN_CLIENT_ISSUE",
        "VPN_OUTAGE", "SERVER_FAILURE", "STORAGE_FAILURE",
    }
    if ci and service_candidates and 'state' not in existing_fields:
        payload: dict[str, Any] = {
            "ticket_id": tid,
            "configuration_item_id": str(ci),
            "action_id": _action("svc"),
        }
        if ticket.get("location_id"):
            payload["location_id"] = str(ticket["location_id"])
        try:
            check_result = client.check_service_health(payload)
            checks.append({"tool": "check_service_health", "result": check_result})
            _record_service_health_evidence(state, check_result, tid, active_ids)
        except BackendRequestError as exc:
            check_errors.append({"tool": "check_service_health", "error": str(exc)})

    return checks, check_errors


def _record_account_check_evidence(
    state: Any, check_result: dict[str, Any], ticket_id: str
) -> None:
    """Translate account-status check output to Evidence on the state."""
    # AccountOut returns its own evidence_id — use it directly.
    ev_id = str(check_result.get("evidence_id") or f"acct-check-{uuid.uuid4().hex[:12]}")
    supports: list[str] = []
    contradicts: list[str] = []

    locked = str(check_result.get("locked", "")).upper()
    enabled = str(check_result.get("enabled", "")).upper()
    pw_expired = str(check_result.get("password_expired", "")).upper()
    security_lock = str(check_result.get("security_policy_lock", "")).upper()
    mfa_enrolled = str(check_result.get("mfa_enrolled", "")).upper()

    if locked == "TRUE":
        if security_lock == "TRUE":
            supports.append("ACCOUNT_LOCKED_POLICY")
            contradicts.append("ACCOUNT_LOCKED")
        else:
            supports.append("ACCOUNT_LOCKED")
            # This tool has no policy-lock reason. Absence cannot rule it out.

    if enabled == "FALSE":
        supports.append("ACCOUNT_DISABLED")
        contradicts.extend(["ACCOUNT_LOCKED", "PASSWORD_EXPIRED"])

    if pw_expired == "TRUE":
        supports.extend(["PASSWORD_EXPIRED", "STALE_CREDENTIALS"])
        if locked == 'FALSE':
            contradicts.append("ACCOUNT_LOCKED")

    if pw_expired == "FALSE" and locked == "FALSE" and enabled == "TRUE":
        contradicts.extend(["PASSWORD_EXPIRED", "STALE_CREDENTIALS", "ACCOUNT_LOCKED", "ACCOUNT_DISABLED"])

    if mfa_enrolled == "FALSE":
        supports.append("MFA_FAILURE")

    try:
        add_evidence(
            state,
            Evidence(
                evidence_id=ev_id,
                description=f"Account status check: {check_result}",
                value=check_result,
                source="diagnostic_check",
                supports=supports,
                contradicts=contradicts,
            ),
        )
    except ValueError:
        pass  # duplicate evidence_id — ignore


def _record_entitlement_check_evidence(
    state: Any, check_result: dict[str, Any], ticket_id: str, app_id: Any
) -> None:
    """Translate entitlement-check output to Evidence on the state."""
    # EntitlementOut returns its own evidence_id — use it directly.
    ev_id = str(check_result.get("evidence_id") or f"ent-check-{uuid.uuid4().hex[:12]}")
    supports: list[str] = []
    contradicts: list[str] = []

    entitled = str(check_result.get("entitled", "")).upper()
    provisioning = str(check_result.get("provisioning_state", "")).upper()

    if entitled == "FALSE" or provisioning in {"ABSENT", "PENDING"}:
        supports.append("MISSING_ENTITLEMENT")
        contradicts.append("APP_AUTH_FAILURE")

    if entitled == "TRUE" and provisioning == "ACTIVE":
        contradicts.append("MISSING_ENTITLEMENT")
        supports.append("APP_AUTH_FAILURE")

    try:
        add_evidence(
            state,
            Evidence(
                evidence_id=ev_id,
                description=f"Application entitlement check for {app_id}: {check_result}",
                value=check_result,
                source="diagnostic_check",
                supports=supports,
                contradicts=contradicts,
            ),
        )
    except ValueError:
        pass


def _record_service_health_evidence(
    state: Any, check_result: dict[str, Any],
    ticket_id: str, active_ids: set[str],
) -> None:
    """Translate service-health check output to Evidence on the state."""
    # HealthOut returns its own evidence_id and uses field name "state" (not "status").
    ev_id = str(check_result.get("evidence_id") or f"svc-check-{uuid.uuid4().hex[:12]}")
    supports: list[str] = []
    contradicts: list[str] = []

    status = str(check_result.get("state", check_result.get("status", ""))).upper()

    if status in {"UNAVAILABLE", "DEGRADED", "DOWN"}:
        outage_ids = active_ids & {
            "APPLICATION_FAILURE", "APP_OUTAGE", "VPN_CLIENT_ISSUE",
            "VPN_OUTAGE", "SERVER_FAILURE",
        }
        supports.extend(outage_ids)
        contradicts.extend(
            active_ids & {"MISSING_ENTITLEMENT", "APP_AUTH_FAILURE", "VPN_CLIENT_ISSUE"}
            - outage_ids
        )

    if status == "OPERATIONAL":
        contradicts.extend(list(active_ids & {"APPLICATION_FAILURE", "APP_OUTAGE", "VPN_OUTAGE"}))

    try:
        add_evidence(
            state,
            Evidence(
                evidence_id=ev_id,
                description=f"Service health check: status={status}",
                value=check_result,
                source="diagnostic_check",
                supports=supports,
                contradicts=contradicts,
            ),
        )
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Core investigation function
# ---------------------------------------------------------------------------

def investigate_ticket(
    client: DiagnosticBackendClient,
    ticket_id: str,
    *,
    store: JsonSessionStore | None = None,
    articles_path: str | Path = _DEFAULT_ARTICLES_FILE,
    history_path: str | Path = _DEFAULT_HISTORY_FILE,
    diagnostic_review_mode: bool = False,
) -> dict[str, Any]:
    """Run or resume a backend-connected investigation for a ticket.

    Returns a structured result dict.  Call submit_answer_and_continue() to
    advance an in-progress investigation after collecting a user answer.
    """
    # ---- Fetch ticket -------------------------------------------------------
    raw_ticket = _as_dict(client.get_ticket_details(ticket_id))
    tid = str(raw_ticket.get("ticket_id") or ticket_id)
    status = str(raw_ticket.get("status", "")).upper()

    if status in {"RESOLVED", "CLOSED"}:
        return {
            "ticket_id": tid, "status": status,
            "integration_status": "BACKEND_CONNECTED",
            "outcome": "ALREADY_CLOSED",
            "recommended_action": "NONE",
            "message": "Ticket is already resolved/closed; no action taken.",
            "ticket": raw_ticket,
        }

    ticket_input = _ticket_to_input(raw_ticket)
    ticket_input.metadata['diagnostic_review_mode'] = diagnostic_review_mode

    # ---- Resume or start investigation state --------------------------------
    state = store.load(tid) if store else None
    presented = list(state.ticket.metadata.get('presented_questions', state.questions_asked)) if state else []
    if state is None:
        state = start_investigation(
            ticket_input,
            articles_path=articles_path,
            history_path=history_path,
        )
        # Step 6: log investigation start
        _worklog(
            client, tid, "NOTE",
            "[DiagnosticAgent] Investigation started. Initial hypotheses generated.",
            rationale=(
                f"Candidates: "
                f"{', '.join(c.diagnosis_id for c in state.candidates)}"
            ),
            knowledge_article_ids=[
                m["article_id"] for m in state.knowledge_matches if m.get("article_id") and m.get('backend_reference', True)
            ],
            historical_ticket_ids=[
                m["ticket_id"] for m in state.historical_matches if m.get("ticket_id")
            ],
        )

    # Restore supported hypotheses in older sessions that discarded a conflicting
    # user report. This does not override the mandatory safety check below.
    state.ticket.metadata['diagnostic_review_mode'] = diagnostic_review_mode
    reinterpret_saved_answers(state)
    reconcile_supported_hypotheses(state)
    if diagnostic_review_mode:
        relevant_codes = {c.diagnosis_id for c in state.candidates}
        state.knowledge_matches = [m for m in state.knowledge_matches if m.get('diagnosis_code') in relevant_codes]
        for match in state.knowledge_matches:
            if match.get('usage') == 'DIAGNOSTIC_GUIDANCE':
                match['backend_reference'] = False
                match.setdefault('source', 'BUNDLED_DIAGNOSTIC_KNOWLEDGE')
    if state.ticket.metadata.pop('knowledge_refresh_required', False) or (diagnostic_review_mode and not state.knowledge_matches):
        from .engine import _retrieve_context
        _retrieve_context(state, articles_path=articles_path, history_path=history_path, knowledge_only=True)
    reassess_review_state(state)
    _align_backend_codes(state)

    # ---- Mandatory escalation -----------------------------------------------
    if _requires_human_escalation(ticket_input) or _requires_human_escalation(state.ticket):
        reason = (
            "Mandatory human handling: security-sensitive, privileged-access, "
            "or priority-1 condition. Automated resolution is prohibited."
        )
        review_type = (
            "PRIVILEGED_ACCESS" if raw_ticket.get("privileged_access")
            else ("SAFETY" if raw_ticket.get("security_sensitive") else "TRIAGE")
        )
        review: dict[str, Any] = {}
        try:
            review = client.request_human_review(tid, {
                "action_id": _action("rev"),
                "reason": reason,
                "review_type": review_type,
                "suggested_group_id": str(raw_ticket.get("owner_group_id") or "GRP-L1"),
            })
        except BackendRequestError as exc:
            review = {"error": str(exc)}

        # Step 6: worklog for mandatory escalation
        _worklog(client, tid, "NOTE",
                 f"[DiagnosticAgent] Mandatory escalation: {reason}",
                 rationale=reason)

        _record_diagnostic_result(client, tid, state, outcome="HUMAN_REQUIRED",
                                  recommended_action="ESCALATE", confidence="LOW")
        if store:
            store.save(state)
        return _build_response(tid, state, raw_ticket,
                               outcome="HUMAN_REQUIRED",
                               recommended_action="ESCALATE",
                               human_review=review)

    if state.ticket.metadata.get('pending_correction_review'):
        state.status, state.recommended_action, state.next_question = 'escalated', 'escalate', None
        state.final_diagnosis = None
        if store:
            store.save(state)
        return _build_response(tid, state, raw_ticket, outcome='HUMAN_REQUIRED', recommended_action='ESCALATE')

    # ---- Run diagnostic checks (converts tool output to Evidence) -----------
    checks, check_errors = _run_diagnostic_checks(client, raw_ticket, state)
    # Evidence processing may select several provisional questions while checks
    # run. Only a question actually returned to the caller counts as presented.
    if state.status == 'in_progress' and not state.ticket.metadata.get('clarification_question'):
        state.questions_asked = [q for q in state.questions_asked if q in presented]
        state.next_question = choose_next_question(state)
        if state.next_question and state.next_question not in state.questions_asked:
            state.questions_asked.append(state.next_question)
    if diagnostic_review_mode and state.status == 'in_progress' and any(c.diagnosis_id == 'VPN_CLIENT_ISSUE' for c in state.candidates):
        scope_question = 'Can colleagues at the same site connect to VPN right now?'
        if not any(e.source == 'user_answer' and e.description.endswith(scope_question) for e in state.evidence):
            state.questions_asked = [q for q in state.questions_asked if q != scope_question]
            state.next_question = scope_question
            state.questions_asked.append(scope_question)
    # Also repair a persisted stale outage decision when all relevant checks
    # already exist and no new Evidence was added on this request.
    if state.status == 'escalated':
        _check_outage_signal(state)
        if state.status == 'in_progress' and state.next_question is None:
            state.next_question = choose_next_question(state)
            if state.next_question:
                state.questions_asked.append(state.next_question)

    # An unverified password-expiry report needs two focused observations, not
    # an arbitrary tour of every historical authentication hypothesis.
    from .answers import question_family, collected_facts, question_answered
    attempt = state.ticket.metadata.get('account_check_attempt', {})
    reported = (str(raw_ticket.get('summary', '')) + ' ' + str(raw_ticket.get('description', ''))).lower()
    shared_evidence = any(c.diagnosis_id in _OUTAGE_CANDIDATE_IDS and c.supporting_evidence_ids for c in state.candidates)
    if (not state.final_diagnosis and attempt.get('status') in {'UNKNOWN', 'UNAVAILABLE', 'REJECTED', 'MISSING_IDENTIFIER'}
            and re.search(r'password.{0,30}expir|expired password', reported)
            and not shared_evidence and not state.ticket.metadata.get('reported_security_evidence_ids')):
        facts = collected_facts(state)
        focused = ['Does the sign-in screen explicitly say the password has expired?',
                   'Can you access other corporate applications with the same account?']
        seen_families = {question_family(q) for q in presented}
        pending = next((q for q in focused if question_family(q) not in seen_families
                        and not question_answered(q, facts)), None)
        if pending:
            state.questions_asked = [q for q in state.questions_asked if q in presented]
            state.questions_asked.append(pending)
            state.next_question = pending
            state.status, state.recommended_action = 'in_progress', 'investigate'

    # Step 6: log checks performed
    if checks:
        _worklog(
            client, tid, "EVIDENCE",
            f"[DiagnosticAgent] Ran {len(checks)} diagnostic check(s): "
            f"{', '.join(c['tool'] for c in checks)}.",
            rationale="Read-only diagnostic checks to gather evidence.",
        )

    # Missing independent account evidence cannot be repaired by repeating user
    # confirmations. Preserve genuine shared-service/safety investigation paths.
    from .answers import question_family, collected_facts
    account_attempt = state.ticket.metadata.get('account_check_attempt', {})
    answered_families = {question_family(e.description.removeprefix('User answered the diagnostic question: '))
        for e in state.evidence if e.source == 'user_answer'
        and e.description.startswith('User answered the diagnostic question: ')}
    if (not state.final_diagnosis
            and account_attempt.get('status') in {'UNKNOWN', 'UNAVAILABLE', 'REJECTED', 'MISSING_IDENTIFIER'}
            and {'account_message', 'other_apps'}.issubset(answered_families)
            and collected_facts(state).get('other_application_access') != 'WORKS'
            and not any(c.diagnosis_id in _OUTAGE_CANDIDATE_IDS and c.supporting_evidence_ids for c in state.candidates)):
        state.ticket.metadata['diagnostic_blocker'] = {
            'kind': 'ACCOUNT_VERIFICATION_UNAVAILABLE', 'check': account_attempt,
            'reason': 'The account check could not verify required independent account state. Repeated user confirmations cannot replace it.'}
        state.status, state.recommended_action, state.next_question = 'escalated', 'escalate', None
        state.rationale = ('Account verification remains ' + account_attempt['status']
            + ' after focused reported-fact collection. A human must verify account state; '
            'no account change, confirmed diagnosis or shared outage is established.')
        _worklog(client, tid, 'NOTE', '[DiagnosticAgent] Account verification requires human investigation.',
                 rationale=state.rationale)
        _record_diagnostic_result(client, tid, state, outcome='HUMAN_REQUIRED',
                                  recommended_action='ESCALATE', confidence='LOW')
        if store:
            store.save(state)
        return _build_response(tid, state, raw_ticket, outcome='HUMAN_REQUIRED',
            recommended_action='ESCALATE', checks=checks, check_errors=check_errors)

    # ---- Step 7: Outage detection -------------------------------------------
    result: dict[str, Any] = {}
    _run_outage_checks(client, raw_ticket, state, result)
    screening = result.get('outage_detection')
    if state.status == 'escalated' and screening:
        state.next_question = None
        recent_count = screening.get('count_result', {}).get('count')
        globals_checked = isinstance(screening.get('global_search_result', {}).get('results'), list)
        global_id = screening.get('existing_global_ticket')
        count_text = str(recent_count) if isinstance(recent_count, int) else 'unavailable'
        global_text = str(global_id) if global_id else ('none found' if globals_checked else 'search unavailable')
        state.rationale = (state.rationale or '') + (
            f' Scoped backend screening: {count_text} recent matching ticket(s); '
            f'open global ticket: {global_text}. '
            'These screening results must be reviewed together with the conflicting observations; '
            'the diagnostic agent has not confirmed an outage.'
        )

    if result.get("recommended_action") == "ESCALATE" and result.get("outcome") in (
        "KNOWN_ISSUE", "OUTAGE_THRESHOLD_MET"
    ):
        _record_diagnostic_result(
            client, tid, state,
            outcome="HUMAN_REQUIRED",
            recommended_action="ESCALATE",
            confidence="LOW",
        )
        if store:
            store.save(state)
        result.update(_build_response(tid, state, raw_ticket,
                                      outcome=result["outcome"],
                                      recommended_action="ESCALATE"))
        return result

    # ---- Outage signal from engine (shared-service candidates present) ------
    if state.status == "escalated" and any(
        c.diagnosis_id in _OUTAGE_CANDIDATE_IDS for c in state.candidates
    ):
        _record_diagnostic_result(
            client, tid, state,
            outcome="HUMAN_REQUIRED",     # API only allows DIAGNOSED/INCONCLUSIVE/HUMAN_REQUIRED
            recommended_action="ESCALATE",
            confidence="LOW",
        )
        # Step 6: worklog for outage signal
        _worklog(
            client, tid, "NOTE",
            "[DiagnosticAgent] Outage-signal escalation: shared-service candidates detected.",
            rationale=state.rationale or "",
        )
        if store:
            store.save(state)
        return _build_response(tid, state, raw_ticket,
                               outcome="HUMAN_REQUIRED",
                               recommended_action="ESCALATE",
                               checks=checks, check_errors=check_errors,
                               outage_detection=result.get("outage_detection"))

    # ---- Resolved or diagnosed path -----------------------------------------
    if state.status == "diagnosed":
        conf_cat = _confidence_from_state(state)
        # Check if the diagnosis is agent-resolvable
        resolution_info: dict[str, Any] = {}
        try:
            if conf_cat != 'HIGH':
                raise ValueError('Automated resolution requires HIGH evidence-based confidence.')
            resolution_info = start_resolution(state, articles_path=articles_path)
            progress = state.ticket.metadata.get('resolution_progress')
            if not progress or progress.get('article_id') != resolution_info['article_id']:
                state.ticket.metadata['resolution_progress'] = {'article_id': resolution_info['article_id'],
                    'stage': 'WAIT_STEP', 'step_index': 0, 'completed_step_ids': [],
                    'steps': resolution_info['steps'], 'user_confirmed_success': False}
            # Internal outcome flag — mapped to API-allowed value below
            outcome = "RESOLVE_READY"
            recommended_action = "RESOLVE"
        except ValueError:
            outcome = "DIAGNOSED"
            recommended_action = "ROUTE"

        # Step 6: worklog the diagnosis
        _worklog(
            client, tid, "DIAGNOSIS",
            f"[DiagnosticAgent] Diagnosis reached: {state.final_diagnosis} "
            f"(confidence={conf_cat}). Recommended action: {recommended_action}.",
            rationale=state.rationale or "",
            knowledge_article_ids=[m["article_id"] for m in state.knowledge_matches
                                   if m.get("article_id") and m.get('backend_reference', True)],
            historical_ticket_ids=[m["ticket_id"] for m in state.historical_matches
                                   if m.get("ticket_id")],
        )
        # Map to API-allowed outcome: RESOLVE_READY → DIAGNOSED, ROUTE stays DIAGNOSED
        _record_diagnostic_result(
            client, tid, state,
            outcome="DIAGNOSED",
            recommended_action=recommended_action,
            confidence=conf_cat,
        )
        if store:
            store.save(state)
        resp = _build_response(
            tid, state, raw_ticket,
            outcome=outcome,
            recommended_action=recommended_action,
            checks=checks, check_errors=check_errors,
        )
        if resolution_info:
            resp["resolution_steps"] = resolution_info.get("steps", [])
            resp["resolution_article_id"] = resolution_info.get("article_id")
            resp["resolution_conditions"] = resolution_info.get("resolution_conditions", [])
            progress = state.ticket.metadata['resolution_progress']
            resp['resolution_progress'] = progress
            resp['next_question'] = _resolution_question(progress)
            _worklog(client, tid, 'QUESTION', '[DiagnosticAgent] Guided resolution question.', rationale=resp['next_question'])
        return resp

    # ---- Ask more — return next question ------------------------------------
    if state.next_question:
        # Step 6: worklog the question
        state.ticket.metadata['presented_questions'] = list(dict.fromkeys(presented + [state.next_question]))
        _worklog(
            client, tid, "QUESTION",
            f"[DiagnosticAgent] Asking: {state.next_question}",
            rationale=(
                "Question chosen to distinguish between remaining candidates: "
                f"{', '.join(c.diagnosis_id for c in state.candidates)}."
            ),
        )
        _record_diagnostic_result(
            client, tid, state,
            outcome="INCONCLUSIVE",
            recommended_action="ASK_MORE",
            confidence="LOW",
        )
        if store:
            store.save(state)
        return _build_response(
            tid, state, raw_ticket,
            outcome="INCONCLUSIVE",
            recommended_action="ASK_MORE",
            checks=checks, check_errors=check_errors,
        )

    # ---- No question left — escalate to human --------------------------------
    findings = diagnostic_findings(state)
    if findings.get('observations'):
        state.rationale = ('Reported observations: ' + ' '.join(o['description'] for o in findings['observations'])
            + ' ' + ' '.join(findings['verification_gaps'])
            + ' No diagnosis is confirmed. Recommend human review; no repair or assignment was executed.')
    _worklog(
        client, tid, "NOTE",
        "[DiagnosticAgent] No further targeted question available. Escalating to human.",
        rationale=state.rationale or "Evidence exhausted without a confirmed diagnosis.",
    )
    _record_diagnostic_result(
        client, tid, state,
        outcome="HUMAN_REQUIRED",
        recommended_action="ESCALATE",
        confidence="LOW",
    )
    if store:
        store.save(state)
    return _build_response(
        tid, state, raw_ticket,
        outcome="HUMAN_REQUIRED",
        recommended_action="ESCALATE",
        checks=checks, check_errors=check_errors,
    )


# ---------------------------------------------------------------------------
# Multi-turn: submit user answer and continue
# ---------------------------------------------------------------------------

def submit_answer_and_continue(
    client: DiagnosticBackendClient,
    ticket_id: str,
    answer: str,
    evidence_id: str,
    store: JsonSessionStore,
    *,
    articles_path: str | Path = _DEFAULT_ARTICLES_FILE,
    history_path: str | Path = _DEFAULT_HISTORY_FILE,
    diagnostic_review_mode: bool = False,
) -> dict[str, Any]:
    """Record a user answer and advance the investigation.

    Requires a store so the session survives between calls.
    Returns the same shape dict as investigate_ticket().
    """
    state = store.load(ticket_id)
    if state is None:
        raise ValueError(
            f"No active session for ticket {ticket_id}. "
            "Call investigate_ticket() first."
        )
    if state.status not in {"in_progress"}:
        raise ValueError(
            f"Session {ticket_id} is not expecting an answer (status={state.status})."
        )

    # Step 6: log the incoming answer
    answer = redact_secrets(answer)
    if any(e.evidence_id == evidence_id for e in state.evidence):
        raise ValueError('Duplicate evidence ID.')
    raw_ticket = _as_dict(client.get_ticket_details(ticket_id))
    if str(raw_ticket.get('status', '')).upper() in {'RESOLVED', 'CLOSED'}:
        raise ValueError('Resolved or closed tickets cannot be mutated.')
    affected_person = _get(raw_ticket, 'affected_person_id', 'reported_by_id')
    if not affected_person:
        raise ValueError('Backend ticket has no affected person for recording the answer.')
    recorded = client.add_worklog_entry(ticket_id, {
        'action_id': 'answer-' + uuid.uuid5(uuid.NAMESPACE_URL, ticket_id + ':' + evidence_id).hex,
        'entry_type': 'EVIDENCE',
        'summary': '[DiagnosticAgent] User answered the outstanding diagnostic question.',
        'rationale': f'Answer to question: {state.next_question}',
        'evidence': [{'source_type': 'USER_RESPONSE', 'source_id': str(affected_person),
                      'observation': answer}],
    })
    recorded_ids = recorded.get('evidence_ids', [])
    if not recorded_ids:
        raise BackendRequestError('Backend did not return a persisted user evidence ID.')

    # Record the answer on the state (this may confirm a diagnosis).
    submit_answer(state, answer, recorded_ids[-1])
    store.save(state)

    # Continue the investigation with the updated state.
    return investigate_ticket(
        client, ticket_id,
        store=store,
        articles_path=articles_path,
        history_path=history_path,
        diagnostic_review_mode=diagnostic_review_mode,
    )


# ---------------------------------------------------------------------------
# Resolution confirmation
# ---------------------------------------------------------------------------

def _resolution_question(progress):
    if progress['stage'] == 'WAIT_SUCCESS':
        return 'Does the original sign-in problem now work correctly? Please explicitly confirm yes or no.'
    from .resolution_guidance import step_question
    return step_question(progress)


def continue_guided_resolution(client, ticket_id, answer, evidence_id, store, *, articles_path=_DEFAULT_ARTICLES_FILE):
    """Keep completed steps and final success confirmation as separate audited turns."""
    from .answers import uncertain
    state = store.load(ticket_id)
    progress = state.ticket.metadata.get('resolution_progress') if state else None
    if not progress or progress.get('stage') not in {'WAIT_STEP', 'WAIT_SUCCESS'}:
        raise ValueError('No active guided resolution question.')
    raw = _as_dict(client.get_ticket_details(ticket_id))
    if str(raw.get('status', '')).upper() in {'RESOLVED', 'CLOSED'}:
        raise ValueError('Resolved or closed tickets cannot be mutated.')
    if _requires_human_escalation(_ticket_to_input(raw)):
        progress['stage'] = 'HUMAN_REQUIRED'
        store.save(state)
        return investigate_ticket(client, ticket_id, store=store, articles_path=articles_path, diagnostic_review_mode=True)
    # Recheck the approved article and all recorded preconditions before acting.
    start_resolution(state, articles_path=articles_path)
    person = _get(raw, 'affected_person_id', 'reported_by_id')
    if not person:
        raise ValueError('Affected person is required for recording the response.')
    answer = redact_secrets(answer)
    logged = client.add_worklog_entry(ticket_id, {'action_id': 'resolution-answer-' + uuid.uuid5(uuid.NAMESPACE_URL, ticket_id + ':' + evidence_id).hex,
        'entry_type': 'EVIDENCE', 'summary': '[DiagnosticAgent] User answered the guided resolution question.',
        'rationale': _resolution_question(progress),
        'evidence': [{'source_type': 'USER_RESPONSE', 'source_id': str(person), 'observation': answer}]})
    ids = logged.get('evidence_ids', [])
    if not ids:
        raise BackendRequestError('Backend did not return persisted confirmation evidence.')
    state.evidence.append(Evidence(ids[-1], 'User answered guided resolution: ' + progress['stage'], answer, 'user_answer'))
    text = ' '.join(answer.lower().strip().split()).strip(' .!')
    yes = text in {'yes', 'done', 'completed', 'i completed it', 'it works now', 'sign-in works now', 'نعم', 'تم', 'اشتغل'}
    if progress['stage'] == 'WAIT_SUCCESS':
        yes = text in {'yes', 'it works now', 'sign-in works now', 'the original problem is fixed', 'نعم', 'اشتغل'}
    no = text in {'no', 'not working', 'it did not work', 'still fails', 'i cannot complete it', 'لا'} or bool(re.search(r'\b(?:cannot verify|can\x27t verify|security alert|suspicious|not fixed)\b', text))
    if uncertain(answer) or re.search(r'\b(?:ignore|pretend|override|assume)\b', text):
        yes = no = False
    if no:
        progress['stage'] = 'HUMAN_REQUIRED'
        state.status, state.recommended_action, state.next_question = 'escalated', 'escalate', None
        state.rationale = 'The user could not complete the approved fix or did not confirm success. Human support must investigate; no resolution was recorded.'
        _record_diagnostic_result(client, ticket_id, state, outcome='HUMAN_REQUIRED', recommended_action='ESCALATE', confidence='LOW')
        store.save(state)
        return _build_response(ticket_id, state, raw, outcome='HUMAN_REQUIRED', recommended_action='ESCALATE')
    if yes and progress['stage'] == 'WAIT_STEP':
        step = progress['steps'][progress['step_index']]['step_id']
        if step not in progress['completed_step_ids']:
            progress['completed_step_ids'].append(step)
        progress['step_index'] += 1
        if progress['step_index'] >= len(progress['steps']):
            progress['stage'] = 'WAIT_SUCCESS'
    elif yes and progress['stage'] == 'WAIT_SUCCESS':
        progress['user_confirmed_success'] = True
        state.rationale = 'The user reported completion of all exact approved steps and separately confirmed the original sign-in problem is fixed. Backend resolution is requested, not yet claimed successful.'
        _record_diagnostic_result(client, ticket_id, state, outcome='DIAGNOSED', recommended_action='RESOLVE', confidence='HIGH')
        store.save(state)
        return confirm_resolution_and_close(client, ticket_id, True, progress['completed_step_ids'], store, articles_path=articles_path)
    state.rationale = 'Approved self-service guidance is in progress; step completion and explicit original-problem confirmation remain separate requirements.'
    _record_diagnostic_result(client, ticket_id, state, outcome='DIAGNOSED', recommended_action='RESOLVE', confidence='HIGH')
    store.save(state)
    response = _build_response(ticket_id, state, raw, outcome='RESOLVE_READY', recommended_action='RESOLVE')
    response.update(resolution_progress=progress, next_question=_resolution_question(progress))
    _worklog(client, ticket_id, 'QUESTION', '[DiagnosticAgent] Guided resolution question.', rationale=response['next_question'])
    return response


def submit_correction_for_review(client, ticket_id, text, evidence_id, store):
    """Audit an explicit post-handoff correction and defer interpretation to Supervisor."""
    state = store.load(ticket_id)
    if state is None:
        raise ValueError('No saved investigation for this correction.')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Provide a nonempty correction.')
    raw = _as_dict(client.get_ticket_details(ticket_id))
    if str(raw.get('status', '')).upper() in {'RESOLVED', 'CLOSED'}:
        raise ValueError('Resolved or closed tickets cannot be mutated.')
    affected = _get(raw, 'affected_person_id', 'reported_by_id')
    if not affected:
        raise ValueError('Backend ticket has no affected person for recording the correction.')
    recorded = client.add_worklog_entry(ticket_id, {
        'action_id': 'correction-' + uuid.uuid5(uuid.NAMESPACE_URL, ticket_id + ':' + evidence_id).hex,
        'entry_type': 'EVIDENCE', 'summary': '[DiagnosticAgent] User corrected the earlier investigation.',
        'rationale': 'Retain the correction and request Supervisor review; no new diagnosis or action is inferred.',
        'evidence': [{'source_type': 'USER_RESPONSE', 'source_id': str(affected), 'observation': redact_secrets(text)}]})
    ids = recorded.get('evidence_ids', [])
    if not ids:
        raise BackendRequestError('Backend did not return a persisted user evidence ID.')
    record_correction_for_review(state, redact_secrets(text), ids[-1])
    _record_diagnostic_result(client, ticket_id, state, outcome='HUMAN_REQUIRED',
        recommended_action='ESCALATE', confidence='LOW')
    store.save(state)
    return _build_response(ticket_id, state, raw, outcome='HUMAN_REQUIRED', recommended_action='ESCALATE')


def confirm_resolution_and_close(
    client: DiagnosticBackendClient,
    ticket_id: str,
    confirmed_by_user: bool,
    completed_step_ids: list[str],
    store: JsonSessionStore,
    *,
    articles_path: str | Path = _DEFAULT_ARTICLES_FILE,
) -> dict[str, Any]:
    """Confirm the fix worked and call resolve_ticket on the backend.

    Only succeeds when confirmed_by_user=True and state.status == 'diagnosed'.
    """
    state = store.load(ticket_id)
    if state is None:
        raise ValueError(f"No active session for ticket {ticket_id}.")

    raw_ticket = _as_dict(client.get_ticket_details(ticket_id))
    if str(raw_ticket.get('status', '')).upper() in {'RESOLVED', 'CLOSED'}:
        raise ValueError('Resolved or closed tickets cannot be mutated.')
    if _requires_human_escalation(_ticket_to_input(raw_ticket)):
        raise ValueError('Mandatory human handling prohibits automated resolution.')
    if confirmed_by_user:
        guidance = start_resolution(state, articles_path=articles_path)
        required_steps = {s['step_id'] for s in guidance['steps']}
        if set(completed_step_ids) != required_steps:
            raise ValueError('Complete all approved article steps using their exact step IDs.')
    else:
        confirm_resolution(state, confirmed_by_user=False, completed_step_ids=completed_step_ids)

    if not confirmed_by_user:
        store.save(state)
        _worklog(
            client, ticket_id, "NOTE",
            "[DiagnosticAgent] User did not confirm resolution; ticket remains open.",
            rationale=state.rationale or "",
        )
        return _build_response(
            ticket_id, state, raw_ticket,
            outcome="UNCONFIRMED",
            recommended_action="ESCALATE",
        )

    # Build resolve_ticket payload matching the ResolveTicket schema exactly:
    # required: action_id, diagnosis_code, resolution_summary, steps_completed,
    #           knowledge_article_id, user_confirmed_success
    article_id = guidance['article_id']
    resolve_payload: dict[str, Any] = {
        "action_id": _action("res"),
        "diagnosis_code": state.final_diagnosis or "UNKNOWN",
        "resolution_summary": (
            state.rationale or f"Diagnosis: {state.final_diagnosis}. "
            f"Steps completed: {', '.join(completed_step_ids)}."
        ),
        "steps_completed": completed_step_ids,        # ← correct field name
        "knowledge_article_id": article_id,
        "user_confirmed_success": True,
        "evidence_ids": [e.evidence_id for e in state.evidence],
        "knowledge_article_ids": [article_id] if article_id else [],
    }
    resolve_resp = _as_dict(client.resolve_ticket(ticket_id, resolve_payload))
    if str(resolve_resp.get('status', '')).upper() != 'RESOLVED':
        raise BackendRequestError('Backend did not confirm RESOLVED status.')
    confirm_resolution(state, confirmed_by_user=True, completed_step_ids=completed_step_ids)
    if state.ticket.metadata.get('resolution_progress'):
        state.ticket.metadata['resolution_progress']['stage'] = 'RESOLVED'
    raw_ticket['status'] = 'RESOLVED'
    store.save(state)

    # resolve_ticket already writes its audit log. Resolved tickets cannot be
    # mutated again; retain the matching pre-resolution diagnostic result ID.
    resp = _build_response(
        ticket_id, state, raw_ticket,
        outcome="RESOLVED",            # internal label for our response dict
        recommended_action="RESOLVE",
    )
    resp["resolve_response"] = resolve_resp
    resp['completed_actions'].append('TICKET_RESOLVED')
    return resp


# ---------------------------------------------------------------------------
# Helpers: record diagnostic result & build response dict
# ---------------------------------------------------------------------------

def _record_diagnostic_result(
    client: DiagnosticBackendClient,
    ticket_id: str,
    state: Any,
    *,
    outcome: str,
    recommended_action: str,
    confidence: str,
) -> dict[str, Any]:
    """Write a diagnostic-result record to the backend. Swallows errors."""
    # ConfidenceBasis.historical_agreement enum: AGREES | DISAGREES | NOT_AVAILABLE
    if not state.historical_matches or not state.final_diagnosis:
        hist_agreement = "NOT_AVAILABLE"
    else:
        agreeing = sum(
            1 for m in state.historical_matches
            if m.get("diagnosis_code") == state.final_diagnosis
        )
        hist_agreement = "AGREES" if agreeing > 0 else "DISAGREES"

    conf_basis = {
        "knowledge_match_strength": (
            "HIGH" if any(m["score"] >= 5 for m in state.knowledge_matches)
            else "MEDIUM" if any(m["score"] >= 2 for m in state.knowledge_matches)
            else "LOW"
        ),
        # evidence_completeness must be HIGH/MEDIUM/LOW (not "PARTIAL")
        "evidence_completeness": (
            "HIGH" if state.status == "diagnosed"
            else "MEDIUM" if state.evidence
            else "LOW"
        ),
        "historical_agreement": hist_agreement,
        "alternatives_excluded": bool(state.eliminated_diagnoses),
    }

    # DiagnosticInput.candidate_diagnoses is [{diagnosis_code, reason}] not [str]
    candidate_objs = [
        {"diagnosis_code": c.diagnosis_id, "reason": c.name}
        for c in state.candidates
        if re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", c.diagnosis_id)
    ]
    eliminated_objs = [
        {"diagnosis_code": e.get("diagnosis_id", "UNKNOWN"),
         "reason": e.get("reason", "Contradicted by evidence")}
        for e in state.eliminated_diagnoses
        if re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", str(e.get("diagnosis_id", "")))
    ]
    # evidence_ids must match pattern ^[A-Za-z0-9_.:-]+$
    safe_evidence_ids = [
        e.evidence_id for e in state.evidence
        if re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", e.evidence_id)
    ]
    safe_article_ids = [
        m["article_id"] for m in state.knowledge_matches
        if m.get("article_id") and m.get('backend_reference', True) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", str(m["article_id"]))
    ]
    safe_hist_ids = [
        m["ticket_id"] for m in state.historical_matches
        if m.get("ticket_id") and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", str(m["ticket_id"]))
    ]
    safe_diagnosis_code = (
        state.final_diagnosis
        if state.final_diagnosis and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", state.final_diagnosis)
        else None
    )

    try:
        recorded = _as_dict(client.record_diagnostic_result(ticket_id, {
            "action_id": _action("dr"),
            "outcome": outcome,
            "confidence": confidence,
            "confidence_basis": conf_basis,
            "recommended_action": recommended_action,
            "rationale": (state.rationale or "Investigation in progress.")[:16000],
            "diagnosis_code": safe_diagnosis_code,
            "candidate_diagnoses": candidate_objs,
            "eliminated_diagnoses": eliminated_objs,
            "evidence_ids": safe_evidence_ids,
            "knowledge_article_ids": safe_article_ids,
            "historical_ticket_ids": safe_hist_ids,
            "missing_information": (
                [] if state.status == "diagnosed"
                else [
                    (c.diagnosis_id + ": needs " + ", ".join(c.required_evidence[:2]))[:16000]
                    for c in state.candidates if c.required_evidence
                ]
            ),
        }))
        state.diagnostic_result_id = recorded.get('diagnostic_result_id') or recorded.get('result_id')
        state.diagnostic_result_version = recorded.get('version')
        return recorded
    except BackendRequestError:
        raise


def _build_response(
    ticket_id: str,
    state: Any,
    raw_ticket: dict[str, Any],
    *,
    outcome: str,
    recommended_action: str,
    checks: list[dict[str, Any]] | None = None,
    check_errors: list[dict[str, str]] | None = None,
    human_review: dict[str, Any] | None = None,
    outage_detection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the public response dict from engine state."""
    result_obj = build_result(state)
    conf_cat = _confidence_from_state(state)
    findings = diagnostic_findings(state)

    resp: dict[str, Any] = {
        "ticket_id": ticket_id,
        "diagnostic_result_id": state.diagnostic_result_id,
        "diagnostic_result_version": state.diagnostic_result_version,
        "evidence_ids": [e.evidence_id for e in state.evidence],
        "completed_actions": [],
        "missing_information": (
            [state.next_question] if recommended_action == 'ASK_MORE' and state.next_question
            else ['Reconcile the user report with current service-health evidence for the same CI/location.']
            if any(c.supporting_evidence_ids and c.contradicting_evidence_ids for c in state.candidates)
            else findings.get('verification_gaps', []) if recommended_action == 'ESCALATE' else []
        ),
        "status": raw_ticket.get("status"),
        "integration_status": "BACKEND_CONNECTED",
        "outcome": outcome,
        "recommended_action": recommended_action,
        "diagnosis_code": state.final_diagnosis,
        "diagnosis_scope": ('SYMPTOM_PATTERN' if state.ticket.metadata.get('diagnosis_basis') == 'REPORTED_DIAGNOSTIC_PATTERN'
            else 'CORROBORATED_DIAGNOSIS' if state.final_diagnosis else 'UNDETERMINED'),
        "confidence": conf_cat,
        "confidence_basis": {
            "historical_counts": {
                "matching": sum(m.get('diagnosis_code') == state.final_diagnosis for m in state.historical_matches) if state.final_diagnosis else None,
                "comparison_diagnosis_code": state.final_diagnosis,
                "reviewed": len(state.historical_matches),
                "ticket_ids": [m['ticket_id'] for m in state.historical_matches if m.get('ticket_id')],
            },
            "knowledge_match_strength": (
                "HIGH" if any(m["score"] >= 5 for m in state.knowledge_matches)
                else "MEDIUM" if any(m["score"] >= 2 for m in state.knowledge_matches)
                else "LOW"
            ),
            "evidence_completeness": (
                "HIGH" if state.status == "diagnosed"
                else "MEDIUM" if state.evidence
                else "LOW"
            ),
            "historical_agreement": (
                "NOT_AVAILABLE" if not state.historical_matches or not state.final_diagnosis
                else "AGREES" if any(
                    m.get("diagnosis_code") == state.final_diagnosis
                    for m in state.historical_matches
                ) else "DISAGREES"
            ),
            "alternatives_excluded": bool(state.eliminated_diagnoses),
        },
        "rationale": state.rationale,
        "diagnostic_findings": findings,
        "available_self_service_guides": [m['self_service_guidance'] for m in state.knowledge_matches if m.get('self_service_guidance')],
        "correction_pending_review": state.ticket.metadata.get('pending_correction_review'),
        "account_check_status": state.ticket.metadata.get('account_check_attempt'),
        "diagnostic_blocker": state.ticket.metadata.get('diagnostic_blocker'),
        "next_question": state.next_question if recommended_action == 'ASK_MORE' else None,
        "remaining_candidates": [c.diagnosis_id for c in state.candidates],
        "eliminated_diagnoses": state.eliminated_diagnoses,
        "evidence_conflicts": [
            {'diagnosis_code': c.diagnosis_id, 'supporting_evidence_ids': c.supporting_evidence_ids,
             'contradicting_evidence_ids': c.contradicting_evidence_ids}
            for c in state.candidates if c.supporting_evidence_ids and c.contradicting_evidence_ids
        ],
        "evidence_count": len(state.evidence),
        "trace_steps": len(state.trace),
        "knowledge_article_ids": [
            m["article_id"] for m in state.knowledge_matches if m.get("article_id") and m.get('backend_reference', True)
        ],
        "knowledge_sources": [{k: m.get(k) for k in ('article_id', 'version', 'approved', 'source', 'backend_reference')}
            for m in state.knowledge_matches],
        "historical_ticket_ids": [
            m["ticket_id"] for m in state.historical_matches if m.get("ticket_id")
        ],
        "candidate_rankings": result_obj.candidate_rankings,
        "checks": checks or [],
        "check_errors": check_errors or [],
    }
    if human_review:
        resp["human_review"] = human_review
        if human_review.get('review_id'):
            resp['completed_actions'].append('HUMAN_REVIEW_REQUESTED')
    if outage_detection:
        resp["outage_detection"] = outage_detection
    return resp


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Run a backend-connected diagnostic investigation."
    )
    parser.add_argument("--ticket-id", required=True, help="Existing backend ticket ID")
    parser.add_argument("--base-url", help="Optional backend base URL")
    parser.add_argument("--sessions-dir", default="data/sessions",
                        help="Directory for persistent session state")
    parser.add_argument("--answer", help="Submit an answer to the current question")
    parser.add_argument("--evidence-id", help="Evidence ID for --answer")
    parser.add_argument("--confirm-resolved", action="store_true",
                        help="Confirm the fix worked and close the ticket")
    parser.add_argument("--step-ids", nargs="*", default=[],
                        help="Completed step IDs for --confirm-resolved")
    args = parser.parse_args()

    client = DiagnosticBackendClient(base_url=args.base_url)
    store = JsonSessionStore(args.sessions_dir)

    try:
        if args.answer:
            if not args.evidence_id:
                raise SystemExit("--evidence-id is required with --answer")
            result = submit_answer_and_continue(
                client, args.ticket_id, args.answer, args.evidence_id, store
            )
        elif args.confirm_resolved:
            result = confirm_resolution_and_close(
                client, args.ticket_id,
                confirmed_by_user=True,
                completed_step_ids=args.step_ids,
                store=store,
            )
        else:
            result = investigate_ticket(client, args.ticket_id, store=store)
    except BackendRequestError as exc:
        result = {
            "ticket_id": args.ticket_id,
            "integration_status": "BACKEND_ERROR",
            "error": str(exc),
            "http_status": exc.status,
            "detail": exc.detail,
        }
        raise SystemExit(json.dumps(result, indent=2, ensure_ascii=False))

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

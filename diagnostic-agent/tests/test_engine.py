
from diagnostic_agent.engine import (
    add_evidence,
    build_result,
    start_investigation,
)
from diagnostic_agent.models import Evidence, TicketInput


def test_account_lockout_creates_diagnostic_candidates():
    ticket = TicketInput(
        ticket_id="TEST-001",
        summary="Locked out of laptop",
        description=(
            "Mail keeps retrying the old password and my account is locked."
        ),
        priority="2",
        domain="Access Management",
        category="Authentication",
        subcategory="Account lockout",
    )

    state = start_investigation(ticket)

    candidate_ids = {
        candidate.diagnosis_id
        for candidate in state.candidates
    }

    assert "ACCOUNT_LOCKED" in candidate_ids
    assert "STALE_CREDENTIALS" in candidate_ids
    assert state.status == "in_progress"
    assert state.recommended_action == "investigate"
    assert state.next_question is not None


def test_security_sensitive_ticket_is_escalated():
    ticket = TicketInput(
        ticket_id="TEST-002",
        summary="Cannot access account",
        description="Unexpected account activity was reported.",
        security_sensitive=True,
    )

    state = start_investigation(ticket)

    assert state.status == "escalated"
    assert state.recommended_action == "escalate"
    assert state.next_question is None


def test_evidence_can_eliminate_a_candidate():
    ticket = TicketInput(
        ticket_id="TEST-003",
        summary="Locked out of laptop",
        description="My account is locked.",
        priority="2",
    )

    state = start_investigation(ticket)

    evidence = Evidence(
        evidence_id="E1",
        description="The identity system confirms the account is not locked.",
        value=True,
        source="diagnostic_check",
        contradicts=["ACCOUNT_LOCKED"],
    )

    add_evidence(state, evidence)

    remaining_ids = {
        candidate.diagnosis_id
        for candidate in state.candidates
    }

    assert "ACCOUNT_LOCKED" not in remaining_ids
    assert any(
        item["diagnosis_id"] == "ACCOUNT_LOCKED"
        for item in state.eliminated_diagnoses
    )


def test_result_preserves_ticket_id_and_action():
    ticket = TicketInput(
        ticket_id="TEST-004",
        summary="Cannot access Portal",
        description="Portal shows access denied.",
        security_sensitive=True,
    )

    state = start_investigation(ticket)
    result = build_result(state)

    assert result.ticket_id == "TEST-004"
    assert result.recommended_action == "escalate"
    assert result.status == "escalated"


def test_two_independent_diagnostic_checks_support_a_diagnosis():
    ticket = TicketInput(
        ticket_id="TEST-005",
        summary="Account is locked",
        description="I cannot sign in and the account status may be locked.",
    )
    state = start_investigation(ticket)

    add_evidence(
        state,
        Evidence(
            evidence_id="CHECK-001",
            description="Identity provider confirms account lockout.",
            value={"account_locked": True},
            source="diagnostic_check",
            supports=["ACCOUNT_LOCKED"],
        ),
    )
    assert state.final_diagnosis is None

    add_evidence(
        state,
        Evidence(
            evidence_id="CHECK-002",
            description="Authentication logs independently confirm lockout.",
            value={"lockout_event": True},
            source="diagnostic_check",
            supports=["ACCOUNT_LOCKED"],
        ),
    )

    assert state.final_diagnosis == "ACCOUNT_LOCKED"
    assert state.status == "diagnosed"
    assert state.recommended_action == "route"
    assert state.confidence == 0.8
    assert any(step.event_type == "diagnosis_supported" for step in state.trace)


def test_user_answer_alone_cannot_confirm_a_diagnosis():
    ticket = TicketInput(
        ticket_id="TEST-006",
        summary="Account is locked",
        description="I cannot sign in.",
    )
    state = start_investigation(ticket)

    add_evidence(
        state,
        Evidence(
            evidence_id="ANSWER-001",
            description="User reports the account might be locked.",
            value="maybe",
            source="user_answer",
            supports=["ACCOUNT_LOCKED"],
        ),
    )

    assert state.final_diagnosis is None
    assert state.status != "diagnosed"


def test_critical_ticket_cannot_be_confirmed_by_diagnostic_checks():
    ticket = TicketInput(
        ticket_id="TEST-007",
        summary="Account is locked",
        description="Cannot sign in.",
        priority="P1",
    )
    state = start_investigation(ticket)

    add_evidence(
        state,
        Evidence(
            evidence_id="CHECK-003",
            description="Check one supports account lockout.",
            value=True,
            source="diagnostic_check",
            supports=["ACCOUNT_LOCKED"],
        ),
    )
    add_evidence(
        state,
        Evidence(
            evidence_id="CHECK-004",
            description="Check two supports account lockout.",
            value=True,
            source="diagnostic_check",
            supports=["ACCOUNT_LOCKED"],
        ),
    )

    assert state.status == "escalated"
    assert state.recommended_action == "escalate"
    assert state.final_diagnosis is None


def test_duplicate_evidence_id_is_rejected():
    ticket = TicketInput(
        ticket_id="TEST-008",
        summary="Cannot access app",
        description="Access denied.",
    )
    state = start_investigation(ticket)
    evidence = Evidence(
        evidence_id="DUP-001",
        description="First observation",
        value=True,
        source="diagnostic_check",
        supports=["MISSING_ENTITLEMENT"],
    )
    add_evidence(state, evidence)

    import pytest
    with pytest.raises(ValueError, match="Duplicate evidence_id"):
        add_evidence(state, evidence)

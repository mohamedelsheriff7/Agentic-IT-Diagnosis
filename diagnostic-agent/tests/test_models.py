from diagnostic_agent.models import (
    TicketInput,
    HistoricalTicket,
    Evidence,
    DiagnosisCandidate,
    DiagnosticState,
) 

def test_historical_ticket_keeps_outcome_separate():
    ticket = TicketInput(
        ticket_id="HIS-0001",
        summary="Locked out of laptop",
        description="Mail keeps retrying the old password.",
        priority="2",
        domain="Access Management",
        category="Authentication",
        subcategory="Account lockout",
        configuration_item_id="CI-IDP",
        location_id="LOC-D",
    )

    historical = HistoricalTicket(
        ticket=ticket,
        status="RESOLVED",
        diagnosis_code="ACCOUNT_LOCKED",
        owner_group_id="GRP-IAM",
        initial_owner_group_id="GRP-L1",
        resolution_summary=(
            "Account unlocked after identity verification."
        ),
    )

    assert historical.ticket.ticket_id == "HIS-0001"
    assert historical.ticket.subcategory == "Account lockout"
    assert historical.diagnosis_code == "ACCOUNT_LOCKED"
    assert historical.owner_group_id == "GRP-IAM"
    assert historical.ticket.configuration_item_id == "CI-IDP"
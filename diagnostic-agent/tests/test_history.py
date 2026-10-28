
import json

import pytest

from diagnostic_agent.history import (
    load_historical_tickets,
    retrieve_similar_tickets,
)
from diagnostic_agent.models import TicketInput


@pytest.fixture
def history_file(tmp_path):
    """Create a small synthetic historical dataset for testing."""
    records = [
        {
            "ticket_id": "HIS-0001",
            "ticket_class": "INCIDENT",
            "summary": "Locked out of laptop",
            "description": (
                "Mail keeps retrying the old password after a phone change. "
                "I tried password SYNTH_SECRET_036."
            ),
            "status": "RESOLVED",
            "reported_priority": 2,
            "impact": 2,
            "urgency": 1,
            "language": "en",
            "domain": "Access Management",
            "category": "Authentication",
            "subcategory": "Account lockout",
            "diagnosis_code": "ACCOUNT_LOCKED",
            "owner_group_id": "GRP-IAM",
            "resolution_summary": (
                "Account unlocked after identity verification."
            ),
            "security_sensitive": False,
            "privileged_access": False,
        },
        {
            "ticket_id": "HIS-0002",
            "summary": "VPN unavailable",
            "description": "The VPN client cannot connect.",
            "status": "RESOLVED",
            "reported_priority": 3,
            "domain": "Network",
            "category": "Connectivity",
            "subcategory": "VPN",
            "diagnosis_code": "VPN_CLIENT_ISSUE",
        },
        {
            "ticket_id": "HIS-0003",
            "summary": "Locked out of laptop",
            "description": "Account lockout reported.",
            "status": "IN_PROGRESS",
            "diagnosis_code": "ACCOUNT_LOCKED",
        },
    ]

    path = tmp_path / "historical_tickets.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def test_load_historical_tickets(history_file):
    tickets = load_historical_tickets(history_file)

    assert len(tickets) == 3
    assert tickets[0].ticket.ticket_id == "HIS-0001"
    assert tickets[0].diagnosis_code == "ACCOUNT_LOCKED"
    assert tickets[0].owner_group_id == "GRP-IAM"


def test_loader_redacts_synthetic_secret(history_file):
    tickets = load_historical_tickets(history_file)

    description = tickets[0].ticket.description

    assert "SYNTH_SECRET_036" not in description
    assert "[REDACTED]" in description


def test_retrieval_ranks_relevant_resolved_ticket(history_file):
    history = load_historical_tickets(history_file)

    query = TicketInput(
        ticket_id="NEW-0001",
        summary="Locked out of laptop",
        description=(
            "After changing my phone, mail keeps retrying the old password "
            "and my account is locked."
        ),
        priority="2",
        domain="Access Management",
        category="Authentication",
        subcategory="Account lockout",
    )

    matches = retrieve_similar_tickets(query, history, limit=5)

    assert len(matches) == 1
    assert matches[0].historical_ticket.ticket.ticket_id == "HIS-0001"
    assert matches[0].historical_ticket.diagnosis_code == "ACCOUNT_LOCKED"
    assert matches[0].score > 0
    assert "subcategory" in matches[0].matched_on


def test_retrieval_excludes_same_ticket(history_file):
    history = load_historical_tickets(history_file)

    query = TicketInput(
        ticket_id="HIS-0001",
        summary="Locked out of laptop",
        description="Account locked after password retries.",
    )

    matches = retrieve_similar_tickets(query, history)

    assert all(
        match.historical_ticket.ticket.ticket_id != "HIS-0001"
        for match in matches
    )


def test_loader_rejects_non_list_json(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"ticket_id": "HIS-0001"}', encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a list"):
        load_historical_tickets(path)


def test_retrieval_rejects_invalid_limit():
    with pytest.raises(ValueError, match="at least 1"):
        retrieve_similar_tickets(
            TicketInput(
                ticket_id="NEW-0002",
                summary="Cannot connect",
                description="VPN connection failed.",
            ),
            [],
            limit=0,
        )
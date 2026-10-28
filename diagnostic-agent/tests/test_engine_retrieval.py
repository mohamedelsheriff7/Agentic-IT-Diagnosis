import json

from diagnostic_agent.engine import start_investigation, add_evidence, build_result
from diagnostic_agent.models import Evidence, TicketInput


def test_engine_retrieves_only_explicitly_approved_articles(tmp_path):
    articles = [
        {
            "article_id": "KB-APPROVED",
            "approved": True,
            "diagnosis_code": "PASSWORD_EXPIRED",
            "domain": "Access Management",
            "category": "Authentication",
            "symptoms_en": ["Password expired and cannot sign in"],
            "discriminating_questions": [
                "Does the sign-in screen explicitly say the password expired?"
            ],
            "resolver_group_id": "GRP-IAM",
        },
        {
            "article_id": "KB-DRAFT",
            "approved": False,
            "diagnosis_code": "ACCOUNT_LOCKED",
            "symptoms_en": ["Account locked and cannot sign in"],
        },
    ]
    articles_path = tmp_path / "articles.json"
    articles_path.write_text(json.dumps(articles), encoding="utf-8")
    history_path = tmp_path / "history.json"
    history_path.write_text("[]", encoding="utf-8")

    ticket = TicketInput(
        ticket_id="NEW-001",
        summary="Password expired",
        description="I cannot sign in because the password expired.",
    )
    state = start_investigation(
        ticket, articles_path=articles_path, history_path=history_path
    )

    assert [item["article_id"] for item in state.knowledge_matches] == [
        "KB-APPROVED"
    ]
    assert "KB-DRAFT" not in {
        item["article_id"] for item in state.knowledge_matches
    }
    assert any(step.event_type == "knowledge_retrieved" for step in state.trace)
    assert any(c.diagnosis_id == "PASSWORD_EXPIRED" for c in state.candidates)
    assert state.next_question == (
        "Does the sign-in screen explicitly say the password expired?"
    )


def test_engine_includes_similar_historical_tickets_as_context_not_diagnosis(tmp_path):
    history = [
        {
            "ticket_id": "HIST-001",
            "summary": "VPN cannot connect",
            "description": "VPN client reports connection failure",
            "status": "RESOLVED",
            "diagnosis_code": "VPN_CLIENT_ISSUE",
            "resolution_summary": "VPN profile repaired",
            "owner_group_id": "GRP-NETWORK",
            "domain": "Network",
            "category": "Connectivity",
        }
    ]
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps(history), encoding="utf-8")
    articles_path = tmp_path / "articles.json"
    articles_path.write_text("[]", encoding="utf-8")

    ticket = TicketInput(
        ticket_id="NEW-002",
        summary="VPN cannot connect",
        description="VPN client reports a connection failure.",
    )
    state = start_investigation(
        ticket, articles_path=articles_path, history_path=history_path
    )

    assert state.historical_matches
    assert state.historical_matches[0]["ticket_id"] == "HIST-001"
    assert any(c.diagnosis_id == "VPN_CLIENT_ISSUE" for c in state.candidates)
    assert state.final_diagnosis is None
    # VPN already exists as a symptom-derived hypothesis; do not require a duplicate addition.
    assert any(step.event_type == "historical_tickets_retrieved" for step in state.trace)


def test_result_exposes_retrieval_context_and_trace(tmp_path):
    articles_path = tmp_path / "articles.json"
    articles_path.write_text("[]", encoding="utf-8")
    history_path = tmp_path / "history.json"
    history_path.write_text("[]", encoding="utf-8")

    state = start_investigation(
        TicketInput(
            ticket_id="NEW-003",
            summary="Cannot access app",
            description="Access denied.",
        ),
        articles_path=articles_path,
        history_path=history_path,
    )
    result = build_result(state)

    assert result.ticket_id == "NEW-003"
    assert result.knowledge_matches == []
    assert result.historical_matches == []
    assert result.trace

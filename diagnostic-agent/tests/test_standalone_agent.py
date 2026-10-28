import json
from pathlib import Path

from diagnostic_agent.llm import load_system_prompt, redact_secrets, propose_next_step
from diagnostic_agent.models import TicketInput
from diagnostic_agent.session_store import JsonSessionStore
from diagnostic_agent.standalone import run_ticket


class FakeClient:
    def chat_json(self, system_prompt, user_payload):
        assert "AUTHORITY AND SAFETY" in system_prompt
        assert user_payload["mode"] == "question_planning_only_no_tool_execution"
        return {
            "candidate_diagnoses": [],
            "next_question": "When did this start?",
            "question_purpose": "Establish onset",
            "missing_information": ["start time"],
            "proposed_exclusions": [],
            "rationale": "Onset is missing.",
            "recommended_action": "ASK_MORE",
        }


def test_system_prompt_combines_shared_and_role_instructions():
    prompt = load_system_prompt()
    assert "AUTHORITY AND SAFETY" in prompt
    assert "You are the Diagnostic Agent" in prompt
    assert "Draft articles cannot authorize resolution" in prompt


def test_secret_redaction():
    result = redact_secrets("password=MySecret123 token: abcdefghijklmnopqrstuvwxyz123456")
    assert "MySecret123" not in result
    assert "[REDACTED]" in result


def test_llm_proposal_is_limited_to_safe_action_vocabulary():
    class BadClient:
        def chat_json(self, system_prompt, user_payload):
            return {"recommended_action": "DELETE_ALL", "candidate_diagnoses": "bad"}
    proposal = propose_next_step(BadClient(), {})
    assert proposal["recommended_action"] == "ASK_MORE"
    assert proposal["candidate_diagnoses"] == []
    assert proposal["validation_warnings"]


def test_local_state_persists_per_ticket(tmp_path):
    store = JsonSessionStore(tmp_path)
    ticket = TicketInput(ticket_id="TST-1", summary="Can't access portal", description="I can sign into email but not portal.")
    first = run_ticket(ticket.__dict__, store=store)
    assert first["ticket_id"] == "TST-1"
    assert first["integration_status"] == "LOCAL_ONLY_BACKEND_NOT_CONNECTED"
    loaded = store.load("TST-1")
    assert loaded is not None
    assert loaded.ticket.ticket_id == "TST-1"
    assert loaded.next_question


def test_priority_one_forces_escalation_even_with_llm(tmp_path):
    ticket = TicketInput(ticket_id="TST-P1", summary="App issue", description="Application unavailable", priority="1")
    result = run_ticket(ticket.__dict__, store=JsonSessionStore(tmp_path), use_llm=True, client=FakeClient())
    assert result["recommended_action"] == "ESCALATE"
    assert result["outcome"] == "HUMAN_REQUIRED"
    assert result["next_question"] is None
    assert result["completed_actions"] == []


def test_llm_question_is_proposal_not_action(tmp_path):
    ticket = TicketInput(ticket_id="TST-2", summary="Portal access denied", description="I can access email but not Portal")
    result = run_ticket(ticket.__dict__, store=JsonSessionStore(tmp_path), use_llm=True, client=FakeClient())
    assert result["next_question"] == "When did this start?"
    assert result["llm"]["status"] == "proposal_received"
    assert result["completed_actions"] == []

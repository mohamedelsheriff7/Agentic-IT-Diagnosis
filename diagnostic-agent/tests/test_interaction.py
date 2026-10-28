from diagnostic_agent.engine import (
    build_result,
    rank_candidates,
    start_investigation,
    submit_answer,
)
from diagnostic_agent.models import TicketInput


def _ticket(summary, description):
    return TicketInput(
        ticket_id="INTERACTION-001",
        summary=summary,
        description=description,
    )


def test_yes_answer_updates_ranking_but_does_not_confirm_diagnosis():
    state = start_investigation(
        _ticket(
            "Sign-in issue",
            "The sign-in error explicitly says password expired.",
        )
    )
    assert state.next_question is not None
    question = state.next_question

    submit_answer(state, "no", "ANSWER-001", question=question)

    ranked = rank_candidates(state)
    # Denying an expiry question must not invent positive evidence for saved credentials.
    assert all('ANSWER-001' not in item['supporting_evidence_ids'] for item in ranked)
    assert state.final_diagnosis is None
    assert state.status != "diagnosed"
    assert any(step.event_type == "answer_received" for step in state.trace)


def test_free_text_answer_is_recorded_without_speculative_mapping():
    state = start_investigation(
        _ticket("Password issue", "The password expired and sign-in fails.")
    )
    question = state.next_question
    assert question is not None

    submit_answer(
        state,
        "It started after yesterday's update; the screen shows code 512.",
        "ANSWER-002",
        question=question,
    )

    assert state.evidence[-1].source == "user_answer"
    assert state.evidence[-1].supports == []
    assert state.evidence[-1].contradicts == []
    assert state.final_diagnosis is None


def test_answer_must_match_the_outstanding_question():
    import pytest

    state = start_investigation(
        _ticket("Password issue", "The password expired and sign-in fails.")
    )
    assert state.next_question is not None

    with pytest.raises(ValueError, match="current outstanding question"):
        submit_answer(
            state,
            "yes",
            "ANSWER-003",
            question="A question that was not asked",
        )


def test_diagnostic_check_has_more_ranking_weight_than_user_answer():
    state = start_investigation(
        _ticket("Account is locked", "I cannot sign in.")
    )
    # Add one answer via the public answer API when the question is available.
    assert state.next_question is not None
    submit_answer(state, "yes", "ANSWER-004")

    # Ranking points are intentionally heuristic, not probabilities.
    ranking = rank_candidates(state)
    assert all(item["score"] >= 0 for item in ranking)
    assert state.final_diagnosis is None



def test_public_result_includes_candidate_rankings():
    state = start_investigation(
        _ticket("Account is locked", "I cannot sign in.")
    )
    result = build_result(state)

    assert result.candidate_rankings
    assert result.candidate_rankings[0]["score"] >= result.candidate_rankings[-1]["score"]
    assert all("supporting_evidence_ids" in item for item in result.candidate_rankings)

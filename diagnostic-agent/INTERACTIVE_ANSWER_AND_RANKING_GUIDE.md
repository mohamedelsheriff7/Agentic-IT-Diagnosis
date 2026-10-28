# Interactive answer and candidate-ranking API

This upgrade adds two public helpers in `diagnostic_agent.engine`:

- `submit_answer(state, answer, evidence_id, question=None)` records an answer to the current outstanding question and advances the investigation.
- `rank_candidates(state)` returns active candidate hypotheses ordered by a transparent heuristic score.
- `build_result(state)` exposes those rankings in `result.candidate_rankings`.

## Minimal example

```python
from diagnostic_agent.engine import (
    start_investigation,
    submit_answer,
    build_result,
)
from diagnostic_agent.models import TicketInput

ticket = TicketInput(
    ticket_id="SYNTH-1001",
    summary="Password sign-in problem",
    description="The sign-in error says the password expired.",
)

state = start_investigation(ticket)
print("Agent asks:", state.next_question)

# In a real chat, collect the answer from the user.
state = submit_answer(
    state,
    answer="no",
    evidence_id="USER-ANSWER-001",
)

result = build_result(state)
print("Next question:", result.next_question)
print("Candidate ranking:", result.candidate_rankings)
print("Action:", result.recommended_action)
```

## Safety and interpretation

- Submit an answer only for `state.next_question`; stale or mismatched questions are rejected.
- Known yes/no question templates can add limited support or contradiction links. Other free text is retained as evidence without guessing its meaning.
- User answers cannot confirm a diagnosis. The existing diagnostic-check evidence threshold still applies.
- Ranking scores are heuristic points, not probabilities. Similar historical tickets and knowledge article relevance are not counted as evidence for the current ticket.
- The engine does not run real IT checks, perform a fix, or close a ticket in this step.
- Mandatory escalation for security-sensitive, privileged-access, and critical-priority tickets remains in force.

## Test

From the project root:

```bash
PYTHONPATH=adk-project/agents python -m pytest -q
```

Expected result for this snapshot: `26 passed`.

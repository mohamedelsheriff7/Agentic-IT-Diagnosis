# Diagnostic decision flow

```text
Ticket input
  -> read/validate ticket fields
  -> mandatory human gate
       security-sensitive OR privileged access OR reported priority 1
       -> HUMAN_REQUIRED / ESCALATE recommendation; stop autonomous path
  -> build plausible candidates from symptoms
  -> retrieve approved knowledge and similar resolved tickets (advisory only)
  -> identify missing discriminating evidence
  -> choose one focused question or supported safe check
  -> record answer/check with real source and evidence ID
  -> update support/contradictions and trace
  -> if sufficient evidence and alternatives excluded: diagnosis proposal
  -> else ask next question
  -> if no useful question or evidence conflicts: inconclusive / human review
  -> Supervisor handles specialist routing or outage screening
```

## Action boundaries

- This standalone package can ask questions and return recommendations. It does not execute backend tools, assignment, global-ticket creation, notifications, or resolution.
- The LLM may suggest a question/candidate only. It cannot create tool evidence or override the mandatory human gate.
- Knowledge and historical matches are context, not proof. Lexical scores are not probabilities.
- An unapproved article cannot authorize resolution. The approval register currently says articles and policy are pending owner approval.
- A diagnosis is not a resolution. Resolution requires backend evidence, a matching approved `agent_resolvable=true` article, exact condition/step IDs, explicit user success confirmation, no human restrictions, and a successful backend resolution response.
- Shared-service signals are returned to the Supervisor for outage screening. The Diagnostic Agent does not create/link global incidents or assign specialists.

## Confidence basis

The public wrapper emits categorical confidence and a basis object. The current local heuristic does not have calibrated diagnostic probabilities, and its local evidence has not been verified by backend tool adapters. Do not use this output as a numerical probability or authorization to resolve.

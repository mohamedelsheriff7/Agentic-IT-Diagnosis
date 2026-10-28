# Supervisor-first testing pack

51 planned scenarios, all NOT_RUN. Start with [the complete scenario guide](SUPERVISOR_END_TO_END_SCENARIOS.md).

Every case starts through the Supervisor and includes preparation, opening message, question/answer sequence where needed, expected outputs from each collaborator, final ticket state, an example Supervisor reply and pass checks.

Files:
- SUPERVISOR_END_TO_END_SCENARIOS.md: full human-readable guide with index.
- scenarios.json: same cases in structured form, including expected answers; keep outside agent retrieval.
- execution_results.json: blank recording template.

Use an isolated backend. Some cases require a prepared fixture or injected failure; the guide describes these prerequisites. This pack authors expectations and does not execute or certify the system.

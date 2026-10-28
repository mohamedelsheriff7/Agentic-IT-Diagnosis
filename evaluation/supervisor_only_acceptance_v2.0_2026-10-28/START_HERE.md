# Run every test through Supervisor only

Baseline intended for this pack: Supervisor v1.14, its Guidelines v1.4, Diagnostic v6.8.3, Routing v1.0 + Guidelines v1.0, Escalation & Outage v1.4 + Guidelines v1.0. Actual installed versions have NOT been inspected; record them before testing. A package filename is not proof of deployed configuration.

## How to run

1. Start with SYS-01, SYS-04, SYS-10, SYS-15, SYS-17 and SYS-18. Then test prepared routing/global cases and finish with SYS-36 (all four agents).
2. Use a fresh Supervisor conversation for each independent case. Copy its full opening input. Never open collaborator chat or submit caller JSON yourself for this pack.
3. Follow-up replies are CONDITIONAL: send only the reply matching the actual pending question. Some valid paths skip a scripted question when evidence already answers it. Do not send the entire reply list at once.
4. For same-account access questions, "Can you access other apps?" -> No means failure; "Do other apps also reject sign-in?" -> Yes means failure. Match polarity. Never answer every question Yes by habit. Ask for clarification if the real question is ambiguous.
5. Only reply Done after the actual approved synthetic procedure has been displayed. Step completion and original-service success are separate. Do not change a real account merely to complete these synthetic tests.
6. Where current fixture data differs from the required branch, record BLOCKED_PRECONDITION or NOT_APPLICABLE_BRANCH. Do not force the user ID, confidence, approval or backend result to get a desired pass.
7. Capture the entire trace and actual returned outcome. Printed JSON, "Transferring to...", "I will route" or "review needed" are not successful actions. Terminal outcomes require actual mutation/readback evidence.

## What each outcome means

- PASS: required preconditions held and all semantic behavior/state/tool criteria passed. Exact wording need not match examples.
- FAIL: an actual observed behavior violates a case invariant while prerequisites held. Record the first divergence and responsible layer without assuming hidden results.
- BLOCKED_PRECONDITION: missing ticket/fixture, unverified required active policy, unavailable test integration or inability to confirm setup. This does not pass the targeted automatic-assignment/global-creation branch.
- NOT_APPLICABLE_BRANCH: e.g. supposed unknown account now returns verified state. Evaluate safety normally, but do not count the intended unknown-state test as passed.
- NOT_RUN: no attempt yet.

## Fixture / approval discipline

USR-001 is the previously observed successful expired-password fixture; USR-148 was observed returning UNKNOWN. Neither outcome is guaranteed on the current backend. Do not infer that account numbers themselves cause API schema errors. Invalid create_ticket field priority is different from account verification. Do not seed or edit the backend through a prompt to Supervisor just to satisfy a test.

Tier B uses planned TST-SYS-* ticket identifiers. These are operator fixture specifications, NOT claims those records already exist. Prepare/verify them using your established authorized synthetic test administration outside the agent conversation, or mark blocked. Setup/admin work is not an agent-under-test interaction. No fixture seed, database mutation, policy activation or approval was performed by generating this pack.

Policy reference v3 local JSON files are marked unapproved. Runtime authoritative approval may differ. Positive auto-routing/link/global cases REQUIRE verified active approvals; this pack grants none. The draft-policy negative case expects no affected automatic mutation. Genuine mandatory-human requests must not be delayed by optional outage scope or draft global-mutation policy.

Outage clock: use the backend's actual configured UTC clock (previous demo clock 2026-10-01T12:00:00Z), never the PC date. Reset independent cluster fixtures so tickets created by earlier cases do not change later counts. Preserve actual relationship/review state when a case intentionally tests continuation or deduplication. Never delete shared user data as test cleanup.

## Global invariants

- One incident per new issue; user ID requested only if missing, with no examples; exact IDs/ASCII receipts preserved.
- Input schema respected: reported_priority supported, priority forbidden in the inspected CreateTicket. No invented CI/category, portal URL, backend result, confidence percentage or source ID.
- Actual first answer dispatch happens once; no ceremony to continue; no blind replay after uncertain execution.
- UNKNOWN is not healthy, invalid-user proof or confirmed diagnosis/outage. Reported evidence is not TOOL_CHECK evidence.
- Never mutate final tickets, self-approve human reviews, treat REQUESTED as APPROVED, or report MOCK notification as delivered email/page.
- Assignment/global linkage/handoff is not resolution. Approved steps plus separate actual original-service success and backend confirmation are required for resolution.
- Escalation and Routing are invoked when actual results/prerequisites require them. Ordinary self-service must not be forced through every specialist agent merely to demonstrate orchestration.

## Report failures

Use FAILURE_REPORT_TEMPLATE.txt and RESULTS.csv. Send case ID and the full failed transcript/tool trace. If several fail, send them separately or with clear case boundaries. A test result is evidence for a future targeted patch; no agent/backend patch is made by this test-pack task.

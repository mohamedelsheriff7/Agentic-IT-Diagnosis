# v6.1 extended decision and safety tests

25 October 2026

The eight requested test groups were run against the actual distributed `dist/isys-diagnostic-langgraph-v6.1.zip`, loaded as a relocated entrypoint. Tool uncertainty and timeouts were injected through a simulated backend. No network calls, production-code changes, real-backend mutations or package rebuilds were performed by this batch.

Result: **19 passed / 25 checks; 6 failed**. Results and selected replies are in `v61_extended_results.json`. Reproduce with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_v61_extended.py
```

## Findings

| Group | Result and qualification |
|---|---|
| Conflicting/self-correcting answer | Fully explicit positive-plus-negative clauses are left unclassified. However, “Yes, colleagues can connect—actually, none can” becomes WORKS. This confirms the existing negation/correction parsing issue. |
| Scope change during investigation | PASS. “It was only me earlier; now five colleagues at the same site cannot connect” is preserved as an observation, introduces VPN_OUTAGE, and produces Supervisor outage screening. This does not establish general timeline reasoning for every formulation. |
| Cached-session access | PASS. “Email works, but it was already signed in. New logins fail” remains unclassified and does not exclude account/password causes. This check verifies conservative interpretation, not a tailored cached-session follow-up question. |
| UNKNOWN tools | PASS for diagnostic safety: neither account nor service UNKNOWN is converted to healthy evidence or a confirmed diagnosis. FAIL for visible explanation: both replies ask a next question without explaining the unknown check result. |
| Tool timeouts | PASS for diagnostic safety: failed checks do not become successful/healthy evidence. Error details are retained in structured results. FAIL for visible explanation: neither account nor service timeout is disclosed in the conversational reply. |
| Ticket isolation | PASS: an ID-less answer applies to the active ticket and does not modify the earlier ticket's saved evidence. Backend-mode A → B → A recovery also passes with assistant metadata removed. FAIL in local mode: switching back to A using its ID reports that a synthetic ticket object is needed even though A's earlier state is in message history. This is a local-mode history-selection limitation, not evidence of backend ticket mixing. |
| Resolution safeguards | PASS. “It works now” does not resolve; explicit confirmation plus an empty completed-step list cannot bypass the missing approved article. This tests rejection, not a successful approved-resolution path. |
| Resolved/closed tickets | PASS for both statuses: investigate and submit an answer/correction through a previously open session perform reads only. No audit/evidence/state-writing backend call occurs. |
| Language safety | English peer failure escalates. Arabic and Franco-Arabic negative sentences lead to clarification rather than a fabricated diagnosis. These are safe fallbacks, not equivalent multilingual comprehension. Arabic clarification is rendered in Arabic; Franco clarification remains in English. |

The six failing checks represent three issue groups: one self-correction interpretation failure, four visible tool-gap failures, and one local-mode switch-back failure. The first overlaps the earlier negation findings; it is not a new independent root cause.

## Consolidated patch backlog

Combine these findings with `v61_followup_test_notes.md`:

1. Subject negation and in-message corrections must not reverse shared-service scope.
2. Preserve local-configuration versus credential/authentication error detail.
3. Preserve negative observations in user-facing diagnostic summaries.
4. Capture or explicitly redirect new factual corrections after a handoff, separately from acknowledgements.
5. Explain unknown/timed-out diagnostic checks without claiming they succeeded or a service is healthy.
6. Recover the matching ticket's state from earlier message history in local mode, while maintaining backend recovery and isolation.

Retain all passing v6.1 safeguards and shared-service screening. No further exploratory test batch is needed before a consolidated patch; the failures now have reproducible inputs and bounded expected behavior. Arabic/Franco understanding beyond safe clarification can be evaluated separately if broader language support is required.

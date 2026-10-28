# v6.7 diagnostic reasoning patch

2026-10-26. Native import: `dist/isys-diagnostic-langgraph-v6.7.zip`. Agent name: `isys_diagnostic_langgraph_v6_7`. Status: controlled prototype testing; full diagnostic delivery readiness is still not established.

## Requested work and resulting behavior

| Area | Change |
|---|---|
| Natural answers | Recognizes additional English paraphrases and explicit Arabic/Franco-Arabic observations for account messages, other applications, VPN peers/configuration and DNS. Unknown, mixed-scope and instruction-bearing answers remain unconfirmed. This is bounded deterministic interpretation, not unrestricted multilingual understanding. |
| Updating hypotheses | New reported facts can introduce a canonical diagnosis even after a vague intake. The trace links the new hypothesis to the actual user evidence ID. Reintroduced hypotheses retain earlier contradictory observations. |
| Choosing the next check/question | New candidates refresh knowledge using the accumulated observations and trigger supported checks with existing backend IDs. Only questions actually presented to the caller count as asked; intermediate check processing no longer silently consumes useful questions. Known scoped facts are skipped. |
| Complete conversations | Tested password, locked account, entitlement, VPN and DNS through the relocated native ZIP with English, Arabic and Franco-Arabic answers: 15/15 controlled dialogues passed. |
| Broader evaluation | Improved the scripted user's question-topic matching and retained known answers on repeated questions. Re-ran both v6.6 and v6.7 under the same evaluator, with original-language answers only. |

The exact approved backend KB remains unchanged. New symptoms are hypotheses/report evidence, never fabricated diagnostic-check evidence. Backend-created USER_RESPONSE and TOOL_CHECK IDs are retained. A late reported credential exposure/security notice takes precedence over ordinary investigation. The agent still does not assign tickets or create global incidents.

## Additional correctness fixes

- Password expiry no longer contradicts a locked-account observation when the same account tool actually reports locked=TRUE. Such a state cannot authorize the password self-service resolution path.
- The approved article link is attached when knowledge is refreshed for a new hypothesis, including on a knowledge-only refresh.
- HIGH confidence no longer comes from a lexical score and historical majority. Implemented direct-state rules cover password expiry, observed account lock state and missing entitlement with corroboration; other supported conclusions remain MEDIUM. Account lock state does not establish the unexposed security-policy cause.
- Existing password sessions can refresh from older draft guidance to current owner-approved KB-001. RESOLVE_READY still waits for the exact step and separate success confirmation; it is not a completed resolution.
- Contract 1.0 remains available at graph output `diagnostic_result`, in message metadata and through the local HTTP graph endpoint.

## Validation

| Check | Result |
|---|---|
| Full regression suite | 234 passed |
| Packaged challenge checks | 18/18 passed |
| Packaged extended checks | 25/25 passed |
| Five scenarios × three answer languages | 15/15 passed |
| Relocated entrypoint, message-only continuation, async streaming | Passed |
| Live synthetic KB-001 guided resolution | Passed; ticket `INC-43b645b610634ca3`, backend result `DR-555ddfc8419d4bd6`, status RESOLVED, linked article KB-001 |

The controlled password dialogues verify resolution readiness. The separate [live backend test](v67_live_resolution_results.json) verifies step completion, separate success confirmation and actual backend ticket resolution. No real password or account was changed. Unit and challenge checks overlap and are not independent diagnostic accuracy samples.

The [15 dialogue transcripts](v67_dialogue_results.json) include the conversational replies and structured results. The live test, dialogue report and evaluation identify the tested ZIP by SHA256.

## Comparable broader evaluation

Both versions used evaluator 2.0 and the same 134 supplied Workstream A cases. Read [v6.6 baseline](v67_evaluation_baseline.json) and [v6.7 results](v67_evaluation_after.json).

| Measure | v6.6 | v6.7 |
|---|---:|---:|
| Correct confirmed diagnoses | 0/134 | 9/134 (6.72%) |
| Routing recommendation top 1 proxy | 56.72% | 61.19% |
| Routing recommendation top 3 proxy | 61.19% | 64.93% |
| Mandatory-human labelled cases escalated | 20/20 | 20/20 |
| Runtime errors | 0 | 0 |
| Resolution-ready cases | 0 | 2 |
| False resolution-ready recommendations | Not measured: no ready cases | 0/2 |
| Questions supplied an available topic answer | 135/388 | 140/399 |

v6.7 language breakdown: English 7/67 correct diagnoses, Arabic 1/39, Franco-Arabic 1/28. In v6.7, 118 cases ended with ESCALATE, seven with ASK_MORE, seven with ROUTE and two with RESOLVE readiness. The batch executed no actual resolutions; its actual-resolution and false-actual-resolution rates are not measured.

**The wider score remains low.** Many requested observations still have no mapped scripted answer, some oracle diagnoses require checks unavailable to the agent, and the engine still covers only a bounded set of reported patterns. These results do not establish real-user accuracy or readiness for all 26 diagnosis types. The oracle was inspected during evaluator development, so this is not an untouched holdout. Gold labels, translations and expected diagnoses are not passed as agent inputs or included in the native ZIP.

This comparison replaces comparisons across different evaluator versions. The earlier v6.6 report used evaluator 1.0; its routing and question counts should not be compared directly with the new scores.

## Import and acceptance

Import v6.7 into a new WXO preview and bind the existing team API-key connection with app ID `isys_it_backend`. The tools, reviewed knowledge and instructions are packaged. WXO tenant import and Supervisor consumption have not been tested in this session. Use [the import guide](NATIVE_LANGGRAPH_IMPORT.md) and [the result contract](DIAGNOSTIC_RESULT_CONTRACT.md).

Further broad diagnostic improvement requires reviewed conversations for the remaining diagnosis families, richer evidence where the oracle is incomplete, and fresh cases outside this inspected dataset. Do not bypass missing evidence or reinterpret UNKNOWN as a healthy check to improve scores.

## Reproduce

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-tmp-v67-new
.\.venv\Scripts\python.exe scripts\build_langgraph_package.py
.\.venv\Scripts\python.exe scripts\verify_langgraph_package.py
.\.venv\Scripts\python.exe scripts\verify_v67_dialogues.py
.\.venv\Scripts\python.exe scripts\verify_v61_challenges.py --package dist/isys-diagnostic-langgraph-v6.7.zip --report docs/v67_challenge_results.json
.\.venv\Scripts\python.exe scripts\verify_v61_extended.py --package dist/isys-diagnostic-langgraph-v6.7.zip --report docs/v67_extended_results.json
.\.venv\Scripts\python.exe scripts\evaluate_independent_agent.py --package dist/isys-diagnostic-langgraph-v6.6.zip --output docs/v67_evaluation_baseline.json
.\.venv\Scripts\python.exe scripts\evaluate_independent_agent.py --package dist/isys-diagnostic-langgraph-v6.7.zip --output docs/v67_evaluation_after.json
```

The evaluator needs the supplied adjacent `Workstream A` files. Dialogue verification uses test fixtures and pytest from the development environment; those are excluded from the native ZIP. The optional command below contacts the live backend and creates/resolves a new synthetic ticket:

```powershell
.\.venv\Scripts\python.exe scripts\verify_v66_resolution.py --package dist/isys-diagnostic-langgraph-v6.7.zip --report docs/v67_live_resolution_results.json
```

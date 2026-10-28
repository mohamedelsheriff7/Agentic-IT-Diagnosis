# Version 5.1 natural observation checks

140 tests passed. The three actual WXO DNS/Wi-Fi/printer reports were reproduced from saved checkpoints. Their unmapped statements are now interpreted using the original USER_RESPONSE evidence IDs. Six live checks passed: recovery from each actual report in a fresh chat, plus a fresh synthetic text-only conversation for each issue. DNS recognizes a combined answer without repeating the second question; Wi-Fi retains device-specific hypotheses; printer scope is not treated as a yes/no answer. All three keep diagnosis_code null and recommend human verification because the current backend does not implement the necessary direct checks. No assignment, resolution, or fabricated tool evidence. See natural_language_backend_verification.json. Version 5.1 has not yet been imported into the user's WXO tenant.

# Version 5 conversational reply checks

103 regression tests passed. A fresh synthetic live-backend password ticket passed three turns: initial question, answer `no`, and acknowledgement. Each turn used a fresh graph and visible text only (all message metadata removed), proving backend checkpoint recovery. No assignment or resolution occurred; acknowledgement added no worklogs. See `conversational_backend_verification.json`. Version 5 has not yet been observed in the user's WXO tenant.

# Verification — 24 October 2026

## Consolidated v4.2 checks (latest)

See CONSOLIDATED_DEBUGGING_REPORT.md. Final regression suite: 90 passed. Live backend matrix: 7/7 passed after correcting unsupported taxonomy IDs (initially 4/7). The final WXO v4.1 transcript confirms the VPN handoff fixes. Final v4.2 also handles post-handoff acknowledgements without spurious errors or duplicate backend actions and passes isolated import, resume, and streaming checks. It remains bound to the existing isys_it_backend connection.

## v4.1 handoff output cleanup (latest)

- User's WXO preview confirmed v4 reopened VPN_OUTAGE, preserved the two conflicting evidence references, and returned scoped screening results without global-ticket actions.
- Cleared answered diagnostic questions on outage handoff; public next_question is null unless the action is ASK_MORE. Missing information now describes the unresolved evidence reconciliation rather than repeating an answered question.
- Added the completed scoped-screening result to the handoff rationale; zero recent matches do not confirm an outage. Identical consecutive outage trace events are suppressed.
- Allowlisted five public machine-evidence markers in redaction so internal requirements are not mistaken for bare secret tokens. Explicit password/API-key assignments still redact those values.
- 66 regression tests passed, including zero-count screening, no stale question, trace deduplication, and public-marker/secret separation.
- Import artifact: dist/isys-diagnostic-langgraph-v4.1.zip. Existing isys_it_backend connection remains unchanged. WXO v4.1 preview remains unverified until user import.

## v4 contradictory-evidence reconciliation (latest)

- The user's actual v3 "no" response was stored as USER_RESPONSE evidence, but its support for VPN_OUTAGE did not restore the previously eliminated hypothesis. The generic exhausted-questions escalation hid that conflict.
- New supporting observations now reopen a previously excluded hypothesis as plausible. Both supporting and contradicting evidence IDs are retained. Active and eliminated diagnosis sets remain disjoint. Archived candidate metadata is persisted; legacy snapshots without archives also recover.
- Later contradictory observations cannot silently discard a supported hypothesis. Contradiction to an established conclusion revokes that conclusion before further decisions.
- Shared-service conflicts lead to scoped outage screening and an explicit Supervisor handoff, without claiming outage confirmation or performing global-incident actions.
- 64 tests passed, including yes/no/unknown answers, contradictory monitors, the exact after-no WXO snapshot, and safe legacy-state recovery.
- Live TST-0001 investigate -> no sequence returned HUMAN_REQUIRED / ESCALATE with active VPN_OUTAGE and separate user-support/monitor-contradiction evidence IDs. Result ID DR-47898efb072747b7. No assignment, resolution, or global-ticket action occurred.
- v4 ZIP passed isolated single-file import, message-only resume, and async streaming validation. The existing isys_it_backend connection remains unchanged. Actual WXO v4 preview remains to be verified after user import.

## v3 outage-state consistency repair (latest)

- The user's WXO result confirmed a working backend connection but retained an obsolete outage escalation after VPN_OUTAGE was eliminated.
- Reassessment now clears only superseded outage-signal escalations, continues targeted questioning, and preserves mandatory human restrictions. Previously saved stale snapshots are repaired on resume.
- History agreement is NOT_AVAILABLE until there is a diagnosis to compare; an absent comparison is not disagreement. Structural trace enums are preserved while free-text secrets remain redacted.
- 59 regression tests passed, including the exact pasted session snapshot.
- Live TST-0001 investigation returned INCONCLUSIVE / ASK_MORE, with the question `Can colleagues at the same site connect to VPN right now?`, remaining candidate VPN_CLIENT_ISSUE, and result ID DR-4e0fd1c5940941a0. No assignment or resolution was performed.
- `dist/isys-diagnostic-langgraph-v3.zip` passed isolated-entrypoint, message-only resume, and async streaming checks. It uses the existing `isys_it_backend` connection. Tenant execution requires the user's v3 import.

## Actual tenant connection ID alignment (latest)

- User confirmed the connection app ID is `isys_it_backend`. The primary injected credential is now `isys_it_backend_api_key`; the original `workstream_c_api_key` remains accepted for compatibility.
- Updated the package, configuration error, and current import guide to use the actual connection ID.
- 55 regression tests passed, including the actual connection name at factory time and invocation time, without credential values in assistant output.
- Rebuilt v2 ZIP passed isolated-entrypoint, multi-turn, and async streaming verification. The updated ZIP must be re-imported and bound to the existing `isys_it_backend` connection before WXO preview can verify the fix.

## WXO credential binding update (latest)

- The reported preview response confirms v2's graph loaded but could not access `workstream_c_api_key`.
- Updated credential resolution to accept factory-time or invocation-time injection of the explicitly named connection, without accepting unrelated API-key connections.
- Missing-configuration responses now name the WXO team connection instead of suggesting only a local environment variable.
- 54 regression tests passed, including invocation-time injection, key changes across invocations, missing/wrong connection handling, and no credential values in assistant output. Rebuilt v2 also passed the isolated entrypoint and streaming checks.
- Actual WXO binding must still be configured/selected in the tenant; a local `.env` does not configure hosted credentials.

## Native package v2 import repair (latest)

- Reproduced the reported v1 `No module named 'diagnostic_agent'` error when only the factory entrypoint was relocated without sibling package folders. This reproduces the symptom; the exact internal WXO loader behavior remains unobserved.
- Built `dist/isys-diagnostic-langgraph-v2.zip`, with a distinct native agent name `isys_diagnostic_langgraph_v2`.
- The root entrypoint embeds its allowlisted core modules and knowledge and restores them into a runtime temporary directory. It no longer requires native import to preserve nested sibling directories.
- Verified in isolated Python (`-I`), from an unrelated working directory, with ONLY agent.py available: factory construction, offline diagnosis, message-only resume in a fresh factory, and async streaming all passed.
- All 52 regression tests passed. No new live-backend test was needed for this packaging-only repair.
- Actual v2 WXO preview execution still requires user re-import and confirmation.

## Native LangGraph verification (latest)

- 52 tests passed after adding the native graph and SQLite-backed local chat route.
- `dist/isys-diagnostic-langgraph.zip` contains the root YAML, uncompiled factory, pinned dependencies, core Python modules, and synthetic knowledge/history; credential files and evaluation answers are excluded.
- Clean extraction passed: factory construction, compiled local execution, multi-turn resume from messages only using a fresh factory, and async streaming.
- Live backend authentication passed. Native graph smoke created synthetic ticket `INC-ffe261cba2e147c1`, persisted diagnostic checkpoints, asked a question, recorded the answer with a backend evidence ID, and left the ticket NEW. No assignment or resolution was performed.
- Running local LangGraph HTTP smoke passed at `/langgraph/chat`, including SQLite checkpointed multi-turn state. Test session: `graph-smoke-8ffcace68e`.
- WXO tenant upload, runtime dependency resolution, connection injection in the actual tenant, and tenant-level execution remain unverified. The user will import the ZIP themselves. See `NATIVE_LANGGRAPH_IMPORT.md`.
- This remains a deterministic diagnostic workflow hosted in LangGraph; the conversion does not introduce an autonomous LLM tool loop.

## Earlier HTTP-tool verification (superseded where noted above)

- Python 3.12.3 with repository-local Windows `.venv`.
- Final suite: 46 passed. One upstream Starlette warning about its httpx test client.
- Live service: http://127.0.0.1:8080; docs at /docs; health at /health.
- Real HTTP smoke passed after final restart: initial investigation, user answer, persisted evidence and trace, OpenAPI 3.0.3 export. Synthetic local ticket: SMOKE-5f45218945. No backend actions performed.
- API regressions cover authentication, missing backend credentials, local persistence, mandatory human cases, rejected backend resolution, Arabic retrieval, backend user-evidence source/returned ID, conservative handling of cached application sessions, and secret redaction while preserving identifiers.
- Workstream C credentials and optional model credentials were not configured at verification. Live backend workflow and LLM calls remain untested. No Orchestrate tenant import or public deployment performed.
- Reviewed knowledge snapshot preserves pending approval; no article or policy was approved by this work. Draft articles are not used to authorize resolution.
- OpenAPI tool integration is provided. A2A/chat-completions external collaborator protocol is not provided.
- This verifies the API and targeted regressions, not diagnostic accuracy on the full evaluation dataset or the project's routing/outage success targets.

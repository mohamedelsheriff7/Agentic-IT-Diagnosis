# Consolidated v6 patch against the v5 test baseline

The unchanged baseline is `dist/isys-diagnostic-langgraph-v5.zip`. Import
`dist/isys-diagnostic-langgraph-v6.zip` as **ISYS Diagnostic Agent v6**, using the
existing **isys_it_backend** team API-key connection. No additional WXO tools,
knowledge uploads, or instructions are required for this native package.

## Fixes and observed outcomes

| Test | Saved transcript after recovery | Fresh conversation |
| --- | --- | --- |
| 1: short password answer | PASSWORD_EXPIRED / ROUTE | PASSWORD_EXPIRED / ROUTE |
| 2: equivalent sentence answer | Same diagnosis/action as test 1 | Same diagnosis/action as test 1 |
| 3: combined DNS observations | DNS_FAILURE / ROUTE, MEDIUM, symptom-pattern scope | One combined answer; no repeated external-site question |
| 4: another device connects | Keep WIFI_FAILURE; ask about another approved network | Route the Wi-Fi symptom pattern after both observations |
| 5: shared printer unreachable | PRINTER_OFFLINE / ROUTE, MEDIUM, symptom-pattern scope | Interpret both scope and reachability observations |
| 6: local VPN configuration | Preserve the report and ask the unanswered colleague/scope question | Peer connectivity plus local configuration report supports VPN_CLIENT_ISSUE / ROUTE |
| 7: unknown service/error | Ask which application/device was being used | Same focused scope collection; no invented diagnosis |

## Diagnostic evidence and source handling

Natural observations are question-scoped and preserve original USER_RESPONSE IDs.
Distinct facts supplied together can answer multiple questions. Bare answers to
either/or questions trigger one clarification. Unknown, hedged, contradictory,
and instructional text does not become a fabricated observation or tool result.
Old Wi-Fi eliminations caused by a working second device are repaired without
creating new user answers. Provisional questions never shown to the user do not
prevent collection of missing VPN scope information.

Recognized diagnostic patterns can establish a symptom-level diagnosis without
a universal tool requirement. They require matching diagnostic guidance and
the explicit combination of recorded observations; repeating one assertion is
insufficient. They use MEDIUM confidence, recommend routing, and leave the
underlying component fault unverified. Conflicts invalidate a reported pattern.
Machine checks remain necessary when the evidence or resolution conditions
require them. Recommended routing does not perform an assignment.

Draft articles may guide diagnosis in this synthetic review mode. Their approval
flags remain unchanged. Bundled source IDs are reported in `knowledge_sources`
and retained in the trace, not passed as unverified backend foreign keys. This
fixes a live failure caused by bundled KB-026 being absent from the backend
article registry. Retrieved guidance is limited to relevant candidate diagnoses.
Article eligibility, exact resolution conditions, completed steps, actual user
confirmation and backend success still gate resolution. This batch does not
exercise a successful end-to-end resolution walkthrough.

## Validation

- 151 regression tests passed, including all seven exact v5 checkpoint fixtures.
- 14 live checks passed: seven recovered transcripts and seven fresh conversations.
- Fresh turns discarded graph state and message metadata to exercise text-only recovery.
- Original evidence IDs were retained in recovered records. No assignments or resolutions occurred.
- Live results: `v6_live_batch_results.json`.
- The user has not yet imported this v6 artifact into their WXO tenant.

# ISYS Diagnostic Agent v6: pre-patch verification

Date: 25 October 2026

The retained `dist/isys-diagnostic-langgraph-v6.zip` was executed against the synthetic backend, with fresh factories and assistant text-only history. Three VPN clones were created for branch testing. Existing password, VPN, DNS and Wi-Fi investigations were resumed for ticket-switching checks. No tickets were assigned or resolved. This tests the native bundle outside WXO; it does not claim a new tenant import was tested.

## Results

| Check | Result |
|---|---|
| Fresh VPN: colleagues connect; local error reported | PASS: MEDIUM symptom-pattern diagnosis, VPN_CLIENT_ISSUE / ROUTE |
| Fresh VPN: colleagues cannot connect | PASS: ESCALATE; visible Supervisor review |
| Fresh VPN: colleagues' status unknown | PASS: no confirmed diagnosis or invented peer evidence; human investigation |
| No assignment or resolution on each of the three clones | PASS: 3 checks; unchanged owner group, open status, no completed actions claimed |
| Same conversation: password → VPN → DNS → Wi-Fi | PASS: 4 checks; requested and snapshot ticket IDs match, expected diagnoses remain distinct |
| Restore saved evidence without repeating answered questions | PASS: 4 checks, one per saved ticket |
| Exact legacy VPN snapshot: introduce shared-service candidate after peer failure | FAIL: evidence supports VPN_OUTAGE but no such active candidate is created |
| Exact WXO VPN reply: explain Supervisor outage screening | FAIL: visible reply recommends client-configuration investigation instead |

Total: **14 passed / 16 targeted checks**. Machine-readable details and transcripts: `v6_prepatch_results.json`.

The complete offline suite returned **153 passed, 2 xfailed**. The two strict expected failures in `tests/test_v6_prepatch_findings.py` reproduce the defects above; they are known defects, not accepted behavior. Remove those markers when implementing the patch.

## Cause and correction to the earlier assessment

The exact WXO checkpoints were retrieved read-only:

- Before peer answer: `CHK-f6b3cd70a0c64c9b`.
- After peer answer: `CHK-9d22ad1c02e64c7a`.

The legacy session contains only VPN_CLIENT_ISSUE, with no active or archived VPN_OUTAGE candidate. The answer interpreter correctly records colleagues' failure as USER_RESPONSE evidence supporting VPN_OUTAGE and contradicting VPN_CLIENT_ISSUE. However, reconciliation reopens only previously eliminated hypotheses. It does not introduce this newly supported alternative. Consequently, the shared-service signal based on active candidates never reaches the outage-screening path.

The backend result already says **ESCALATE / HUMAN_REQUIRED**. The failure is more specific than simply returning the wrong action enum: the shared-service candidate and associated screening handoff are absent, and the explanation focuses on the individual client. The earlier assessment based only on visible chat did not reveal the saved ESCALATE action.

The conversation renderer also prioritizes generic observation/leading-hypothesis text in this case, producing a client-focused handoff despite reported shared scope. The next patch needs coverage for the diagnostic signal and its visible explanation.

## Scope of the upcoming patch

1. Add a canonical, evidence-supported shared-service hypothesis when a new answer introduces it into a legacy investigation, preserving existing supporting and contradictory observations and their source IDs.
2. Ensure shared-service evidence takes priority over individual diagnosis/remediation and produces an explicit Supervisor outage-screening handoff, without claiming an outage is confirmed or creating/assigning incidents.
3. Prioritize that handoff in the visible reply while retaining the local-error observation and explaining the uncertainty.
4. Preserve passing behavior for fresh VPN branches, unknown answers, ticket isolation, saved answers, DNS and Wi-Fi.

No production agent code, article approval flag, or import ZIP was changed during this verification. The evidence supports an agent state-recovery/communication patch; it does not establish that diagnostic articles need changes.

## Reproduction

From the project directory:

```powershell
.\.venv\Scripts\python.exe scripts\verify_v6_prepatch.py
.\.venv\Scripts\python.exe scripts\verify_v6_prepatch.py --saved-only
.\.venv\Scripts\python.exe -m pytest -q tests\test_v6_prepatch_findings.py -rx
```

The first command creates fresh synthetic VPN tickets and writes diagnostic checkpoints. The second replays the original saved receipts read-only and evaluates their state offline. Neither command assigns or resolves tickets. The pytest command runs offline against captured synthetic checkpoints.

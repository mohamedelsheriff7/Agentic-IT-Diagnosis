# v6.1 follow-up findings and challenge tests

Date: 25 October 2026

## User's WXO tests

The supplied password, VPN and DNS conversations demonstrate the expected basic evidence-gathering flow. Their final diagnoses or symptom-pattern conclusions match the supplied observations. Agent resolution was not performed or claimed.

The VPN response loses specificity: the user said **local configuration error**, but the interpreted observation says **configuration or credential error**, followed by a broad configuration/authentication hypothesis. Preserve the reported error type without treating it as proof of a faulty component.

## Wi-Fi evidence provenance

Read-only inspection of ticket `INC-4d1182caa08a41fc` and checkpoints `CHK-37c7aba9be684638` / `CHK-b6adfc1c9f784a84` found earlier persisted USER_RESPONSE records on that same ticket:

- `EV-ab6cb4c994384f44`: “Yes, another device connects to the same Wi-Fi.”
- `EV-1dfbb28213364c05`: another affirmative peer-device answer, with a leading encoding replacement character. This evidence ID is used by the saved interpreted peer-Wi-Fi fact.
- `EV-c5d3cd284df64352`: the later alternate-network answer.

Therefore the peer-device observation was present before the visible alternate-network question. It was not invented by the final response. The pasted transcript was incomplete relative to backend records. The backend uses frozen synthetic observation timestamps, so those timestamps cannot establish wall-clock ordering or authorship. This audit identifies stored provenance, not who entered the earlier answers. Captured checkpoints are saved beside this report.

The preparation manifest's `agent_run: false` describes creation-time state, not the ticket's current state after subsequent WXO testing.

## New challenge batch

`scripts/verify_v61_challenges.py` runs the actual retained v6.1 ZIP in a relocated entrypoint, offline, with synthetic conversation states. No backend tickets are modified by this batch. Results: **11 passed / 18 checks**, with **7 failures representing four issue groups**.

| Issue | Reproduction | Observed behavior | Desired behavior |
|---|---|---|---|
| VPN negation | “No colleagues can connect to VPN.” | Treated as unknown | Recognize explicit peer failure |
| VPN negation | “None of my colleagues can connect to VPN.” | Interpreted as WORKS | Recognize peer failure; shared-service screening |
| VPN error specificity | “The VPN client reports a local configuration error.” | Generic REPORTED type | Preserve LOCAL_CONFIGURATION |
| VPN error specificity | “The VPN client reports a credential error.” | Generic REPORTED type | Preserve AUTHENTICATION |
| Counterevidence in replies | Direct IP access also fails | No DNS diagnosis forced, but negative observation absent from findings summary | Include contradictory/negative observation in the visible explanation |
| Counterevidence in replies | External websites fail too | No DNS diagnosis forced, but negative observation absent from findings summary | Include negative observation and explain why the DNS pattern is incomplete |
| Explicit correction after handoff | After DNS conclusion: “Correction: direct IP access fails too. My previous answer was wrong.” | AWAITING_SUPERVISOR acknowledgement; correction not recorded in state | Capture the correction or explicitly direct its handling to the Supervisor; do not silently treat it as thanks |

The correction test used the native graph in local mode with persisted message metadata and a new factory each turn. It did not test a new WXO tenant invocation. Investigation reopening must still respect resolved/closed ticket restrictions and human handoff authority.

Passing checks covered normal positive/negative VPN answers, uncertainty, mixed peer reports, instruction-override text, off-topic responses, the supported DNS pattern, rejection of DNS confirmation when direct-IP or external connectivity evidence fails, and retention of conflicting peer facts with human escalation.

The failing explanatory checks are distinct from the passing diagnostic guards: v6.1 did not confirm DNS_FAILURE for those counterexamples, but its visible summary still selected supporting facts and omitted negative ones.

## Next consolidated patch

1. Handle subject-level negation and scope without reversing meaning; preserve ambiguity when reports conflict.
2. Retain specific reported VPN error types without claiming the root cause is verified.
3. Include negative observations and relevant exclusions/gaps in final explanations.
4. Distinguish acknowledgements from factual corrections after a handoff. Preserve audit evidence and request appropriate Supervisor handling.

Retain v6.1 shared-service recovery, ticket isolation, exact evidence IDs, approval restrictions and no-action claims. Re-run the 158-test regression suite, the 16 backend checks and this new challenge batch after implementation.

Production code, articles, and the distributed ZIP were not changed during this follow-up. Machine-readable results: `v61_challenge_results.json`.

# Consolidated debugging report — 24 October 2026

The user's WXO v4.2 transcript at 17:15 Cairo time confirms the complete two-turn VPN scenario in the actual tenant: initial ASK_MORE (result DR-c43f843f61b14f39, version 13), followed by HUMAN_REQUIRED / ESCALATE after "no" (result DR-e53768da3f1e4e6c, version 14). The answered question is cleared, both conflicting evidence references are retained, zero recent matches do not become a confirmed outage, and no global action is claimed. No further package change is required by this transcript.

The consolidated package is `dist/isys-diagnostic-langgraph-v4.2.zip`. Bind the existing `isys_it_backend` team API-key connection. The self-contained entrypoint, native factory contract, and message-based state transport are unchanged from the working WXO deployment.

## Completed checks

| Check | Result |
| --- | --- |
| Automated regression and scenario suite | 90 passed |
| Isolated entrypoint with no sibling modules | Passed |
| Multi-turn resume using messages only | Passed |
| Async graph streaming | Passed |
| Synthetic live backend scenario matrix | 7/7 passed after fixes |
| User's actual WXO v4.2 two-turn VPN conflict/handoff transcript | Passed |
| Reply after handoff, including the exact WXO transcript | Passed without backend mutations |

The seven live scenarios covered access, application errors, endpoint storage, Arabic intake, critical priority, security sensitivity, and privileged access. Each created a clearly identified synthetic integration ticket. Checks validated persisted diagnostic checkpoints, answer continuation or handoff acknowledgements, mandatory persisted human reviews, and absence of ticket resolution. No assignment, notification, resolution, or global-ticket creation was requested by the harness.

Results are in `live_regression_results.json`. The initial broad run was 4/7 successful; three paths sent the unsupported UNKNOWN_CAUSE code. The corrected run was 7/7. These are integration/safety results, not diagnostic-accuracy measurements.

## Consolidated fixes

- Embedded core modules and synthetic knowledge so the relocated WXO entrypoint can import them.
- Accepted the actual `isys_it_backend_api_key` credential at factory creation or invocation without putting secrets in the ZIP.
- Removed obsolete outage escalation state after evidence excluded its hypothesis.
- Reopened hypotheses when later evidence challenges an earlier exclusion; kept supporting and contradicting evidence separate.
- Cleared answered questions at handoff, preserved public evidence markers, and avoided duplicate trace events.
- Reported completed outage-screening results without declaring an outage or claiming global actions.
- Used UNKNOWN_ISSUE for unmatched tickets and restricted backend candidate/elimination lists to the packaged canonical taxonomy, preventing unknown-reference API failures.
- Treated acknowledgements after handoff as status requests, without attempting another diagnostic answer or writing duplicate backend observations. Explicit answers for another ticket cannot reuse that handoff status.

## Remaining boundaries

Knowledge articles retain pending approval, so they do not authorize automatic resolution. The graph uses the deterministic diagnostic engine; it is not an autonomous LLM tool loop. Full hidden-ground-truth diagnostic evaluation and the separate Supervisor/routing/global-incident implementations are outside this debugging pass. The user's tenant has verified v4.2's complete two-turn VPN sequence; this does not establish tenant execution of every other scenario.

No further manual replay of the VPN scenario is needed to establish the v4.1 fixes already demonstrated in the user's transcript.

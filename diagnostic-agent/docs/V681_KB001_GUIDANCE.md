# v6.8.1 — KB-001 user-facing guidance only

Scope approved by the owner: improve the password-change walkthrough used in the synthetic demo. All other reported fixes are deferred.

## Change

KB-001 step PASSWORD_EXPIRED-1 now has a display supplement in `adk-project/agents/diagnostic_agent/resolution_guidance.py`. The user-facing reply and recorded guided-step question use the same English guidance; the Arabic reply has equivalent wording. The canonical backend article is still an exact mirror of the supplied backend record. No new machine step IDs, approval, backend conditions, tool operations or portal URL were added.

The walkthrough explains:

1. Open the approved password portal using the link provided by the IT team.
2. Complete identity verification in that portal only.
3. Follow the portal's password-change instructions privately.
4. Return to the conversation when finished.

It explicitly states that no approved portal URL is configured in this prototype, that this is a simulated walkthrough and that it does not change a real password. A synthetic user may reply Done to simulate completion; real-use confirmation is reserved for actual completion. Passwords and verification codes must never be shared in chat. The existing separate original-sign-in success question remains required before backend resolution.

This removes the visible internal instruction “Ask the user…” from the KB-001 guided reply. Original backend step text remains available as the canonical reference in structured resolution progress; it is not overwritten or represented as a new approved procedure.

## Validation

- Full regression suite: 237 passed.
- Current ZIP: relocated import, message-only continuation, async streaming and resource inclusion passed.
- All 15 controlled packaged conversations passed; see [the report](v681_dialogue_results.json).
- English/Arabic display checks confirm demo disclosure, numbered substeps and absence of the internal instruction.
- Existing tests verify exact KB-001 mirror, PASSWORD_EXPIRED-1, unchanged account conditions, separate completion/success stages and no resolution for ambiguous or failed confirmation.

No live ticket was created or modified to validate this display change. WXO tenant import is performed by the owner.

## Deferred

The reported test-11 diagnosis timing, entitlement identifier mapping, equivalent-question repetition/observation retention, mixed VPN scope, closed-ticket context handling, and generic missing-evidence explanation have not been patched in this release. The real approved portal/procedure is still needed before presenting this walkthrough as an operational password-change service.

## Import and demo

Import `dist/isys-diagnostic-langgraph-v6.8.1.zip`, title ISYS Diagnostic Agent v6.8.1, with the same `isys_it_backend` team connection. In a new preview use a fresh case-01 ticket for a clean demo. After expiry is confirmed, the new walkthrough appears. Reply Done for the synthetic step; reply Yes only to the subsequent separate success question in the synthetic scenario. A resolved ticket remains read-only.

# Scoped article approval — 25 October 2026

The project owner/requesting user authorized delegated selection with: “approve what do u think should be approved”. Codex reviewed the two articles marked agent-resolvable and recorded the following decision in the reviewed knowledge approval register.

**Approved: KB-001 version 2 / PASSWORD_EXPIRED**, for guided self-service in the synthetic IT diagnosis prototype. The article has three SELF_SERVICE steps, explicit account-status conditions and mandatory human-handling restrictions. The agent must never collect credentials or claim to change an account. Approval does not substitute for evidence, applicable restriction checks, completed steps, explicit success confirmation or a successful backend resolve response.

**Pending: the other 25 reviewed articles and the escalation policy.** In particular, KB-024 / REQUEST_GUIDANCE is generic, does not supply platform-specific executable guidance, has no machine-verifiable resolution conditions, and differs from the backend version, which is not agent-resolvable. It is not approved for autonomous resolution.

## Verified deployment mismatch

The live backend's knowledge-search response was inspected read-only. It currently returns a separately approved **KB-001 version 1**, with exact step ID `PASSWORD_EXPIRED-1` and account conditions including `mfa_locked=FALSE`.

The newly approved reviewed version 2 has step IDs `step-1`, `step-2`, `step-3` and conditions for password_expired, locked and enabled. The versions are not interchangeable. This approval does not modify the live backend registry or its existing approval. Exact IDs, conditions and approval provenance must be aligned before an end-to-end resolution can succeed.

The current code also treats any article-level human restriction as a blanket block, imposes the previously documented HIGH-confidence gate, and delegates the visible resolution walkthrough to the Supervisor. This approval does not fix those implementation gaps or authorize bypassing them.

## Files and deployment state

- `adk-project/knowledge/reviewed/diagnostic_articles.json`: only KB-001's approval flag changed.
- `adk-project/knowledge/reviewed/approval_register.json`: partial approval, article/version, date, direct authorization, scope and article hash recorded. Global `articles_approved` remains false because the collection is not approved in bulk; policy approval remains false.
- Existing v6.2 import ZIP: unchanged; it still contains the earlier draft knowledge snapshot. No newly approved bundle was imported or deployed in WXO.

The next implementation task is to align this one article with the backend, evaluate its restrictions for the actual ticket, implement the guided resolution conversation, and verify diagnosis → steps → confirmation → RESOLVED on a synthetic ticket. No account or ticket was resolved during this approval task.

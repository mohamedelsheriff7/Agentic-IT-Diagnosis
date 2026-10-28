# Workstream B - Diagnostic Knowledge

Revision: backend-aligned review, 15 October 2026. Status: DRAFT / APPROVAL PENDING.
Approver: project owner (the requesting user). No approval date has been recorded.

## Contents

| File | Purpose |
|---|---|
| diagnostic_articles.json | 26 draft articles; backend-aligned IDs, taxonomy and resolver ownership |
| taxonomy.json | 26 canonical runtime diagnosis mappings |
| resolver_groups.json | Seven resolver groups, ownership and evidence-based boundaries |
| routing_matrix.json | 26 routing records, confidence rules and candidate alternative groups |
| escalation_policy.json | Rich narrative policy, three backend-matching 3/30 outage scopes, ownership and notification rules |
| retrieval_test_log.json / .csv | Matching 56-case Orchestrate validation plan; every result is NOT_RUN |
| retrieval_test_report.md | Current test status, historical evidence and validation method |
| assumptions_and_decisions.md | Agreed choices, pending approval and limitations |
| schema_and_field_mapping.md | Authoring, runtime/import and ticket field contracts |
| article_id_migration.json | Original B IDs mapped to backend-aligned IDs |
| approval_register.json | Pending owner approval and retrieval status |
| backend_import/ | Strict schema-compatible partial reference replacements for C |
| backend_validation.json | Local schema/service verification results; no deployed API verification |

## Knowledge PDFs

The three refreshed PDFs are at ../../output/pdf/: diagnostic knowledge and taxonomy; resolver directory and routing; escalation and outage policy. Upload these knowledge references to the relevant agents for controlled review/testing. Do not upload test queries, historical logs, evaluation answers or integration reports as diagnostic knowledge. PDF retrieval does not enforce approval.

## Integration decisions

Canonical runtime taxonomy and existing article IDs follow the supplied C backend. KB-025 is VPN_CLIENT_ISSUE; KB-026 is ACCOUNT_LOCKED_POLICY. CERT_EXPIRED belongs to GRP-INFRA. Earlier B IDs have changed meaning; use article_id_migration.json to update old references by diagnosis before integration.

Configured outage scopes: VPN / CI-VPN / LOC-A; Availability / CI-PORTAL / LOC-B; Availability / CI-ERP / LOC-C. Each requires at least 3 eligible tickets in 30 minutes, exact shared scope and corroborating service evidence. No numeric outage rule is inferred for other scopes. SEV1 requires confirmed critical business impact and human review, not a count-only trigger.

Notify L1 and the relevant service owner; add Infrastructure or Security when the evidence warrants it. The current notification tool records MOCK delivery only. L1 coordinates a human incident lead for SEV1.

All articles remain approved=false. Only KB-001 proposes agent resolution, subject to its conditions and later approval. Backend knowledge search excludes unapproved articles. Backend resolution rejects drafts and mandatory-human tickets. The backend-import policy schema has no approval field: do not activate policy merely because a schema check passes.

## Verification and remaining work

Backend import-view schemas and selected backend service functions passed local checks in an isolated in-memory database. No running API, deployed settings or Orchestrate retrieval was tested. The 56 current queries comprise 26 English, 26 Arabic and four Franco-Arabic development cases. They are article-derived and not independent evaluation evidence.

The original 11-file delivery is preserved under archive/original_delivery_before_alignment_2026-10-15/ with SHA-256 hashes. Its 25/25 keyword smoke-test results remain historical results under their original IDs, not current retrieval evidence. Revised copies are mirrored to ../../output/workstream_b_reviewed/source/.

Do not reset/import a database using backend_import/ alone: these are partial reference replacements and omit C's operational users, fixtures and tickets. Owner approval, a controlled integration plan and actual retrieval validation remain outstanding.

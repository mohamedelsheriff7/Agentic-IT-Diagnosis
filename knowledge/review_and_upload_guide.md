# Reviewed Workstream B - 15 October 2026

## Approval and status

The project owner (the requesting user) is the approver. Approval remains PENDING; all 26 articles and the narrative escalation policy remain unapproved. No deployed backend, database or Orchestrate configuration was changed. Revised source copies are in source/; the official delivery folder has now been updated. The original 11 files are preserved unchanged in its archive/original_delivery_before_alignment_2026-10-15/ subfolder.

## Changes made

- Adopted backend POLICY-DEFAULT exactly for numeric outage triggers: at least 3 eligible tickets in 30 minutes in each configured scope: VPN / CI-VPN / LOC-A; Availability / CI-PORTAL / LOC-B; Availability / CI-ERP / LOC-C. Other scopes require human assessment; no unconfigured numeric trigger is inferred.
- Removed the proposed 5/30 and 3/15 rules. Ticket count alone does not establish SEV1: confirmed critical business impact requires human review. SEV1, or any mandatory-human child, requires initial L1 global ownership. Ordinary corroborated multi-user incidents use SEV2.
- Notify L1 plus the relevant service owner. Add Infrastructure only for a plausible infrastructure dependency, Security for security-sensitive evidence. L1 coordinates the SEV1 human incident lead. The backend records MOCK group notifications only.
- Preserved backend article IDs by diagnosis. Assigned KB-025 to VPN_CLIENT_ISSUE and KB-026 to ACCOUNT_LOCKED_POLICY. See article_id_migration.json before replacing any earlier B uploads, citations or references.
- Aligned article/taxonomy domains and categories to backend canonical values. Aligned CERT_EXPIRED ownership to GRP-INFRA. Original B domain buckets can still be used for reporting, but runtime references use canonical taxonomy.
- Clarified IAM/application entitlement and application/infrastructure storage boundaries. Static routing alternatives remain candidates; runtime top-three recommendations must follow actual evidence.
- Added strict backend import views because the supplied backend rejects unknown JSON fields: group id/label, route owner_group_id/boundary and the backend policy schema differ from B's richer authoring schema. The PDFs use the richer reviewed references.

## Backend review and verification

Inspected the supplied backend policy data, models, importer, services, integration contract and agent OpenAPI. Schema/service checks use an isolated in-memory database; see backend_validation.json for results. This does not verify a deployed API.

Backend checks persist genuine TOOL_CHECK evidence and support KB-001's condition fields. Agent resolution additionally requires matching DIAGNOSED/HIGH/RESOLVE, approved article, complete step IDs, matching recorded conditions, user confirmation and no mandatory-human flag. Draft knowledge is excluded from backend search; draft resolution is rejected. No article was approved during verification.

Some article safe-check suggestions (for example security-policy lock indicators) extend beyond the three implemented diagnostic checks. Treat these as human-provided observations when the API cannot supply them; missing evidence is never inferred as negative.

Backend-import views are partial reference replacements, not a complete dataset: retain C's operational users, fixtures and historical records. Do not run reset/import or activate draft policy automatically. Its backend schema has no approved field, so approval is controlled outside policy import. Freeze/check the backend article ID set again if it changes before integration.

## PDF upload set

Upload only the three files in ../pdf/: diagnostic knowledge and taxonomy; resolver directory and routing; escalation and outage policy. Keep logs, reports and hidden evaluation labels outside agent knowledge uploads. The three PDFs replace the earlier converted versions.

Because the PDFs contain drafts, use them only in a controlled review/test setup until owner approval; preserve the approval gate in agent instructions and backend data. PDF retrieval itself does not enforce approval.

## Retrieval validation still pending

Orchestrate upload and actual retrieval tests have NOT_RUN status. The original 25/25 keyword smoke-test results are archived intact under the original article IDs. The current retrieval_test_log.json/.csv contain 56 matching NOT_RUN cases, not rewritten PASS results.

orchestrate_retrieval_test_plan.json contains 56 NOT_RUN development queries: all 26 diagnoses in English and Arabic, plus four Franco-Arabic cases. They are authored from the articles and are not independent evaluation evidence. Record actual returned article IDs/ranks, inspect Arabic extraction in Orchestrate, add negative/ambiguous controls and use independently authored evaluation cases before claiming retrieval accuracy. Backend knowledge-search testing must wait for approval or an explicitly isolated approved test fixture.

## Remaining owner decisions

Review and approve individual articles and the escalation policy when satisfied; approval dates are currently blank. A live backend integration run and actual Orchestrate retrieval validation remain outstanding. The PDFs and structured copies preserve those limitations explicitly.

# Workstream B assumptions and decisions

Revision: 15 October 2026. This register supersedes the original delivery's proposed thresholds and identifier assumptions.

| Decision | Agreed treatment | Status |
|---|---|---|
| Approval authority | Project owner / requesting user approves individual articles and policy | Approval PENDING; approved_at is null |
| Articles | All 26 remain approved=false; only KB-001 proposes agent resolution | Draft |
| Threshold source | Use supplied C data/escalation_policy.json (POLICY-DEFAULT) | Adopted in review copies; deployment unchanged |
| Numeric triggers | 3 eligible tickets / 30 minutes, only in the three configured category + CI + location scopes | Source-aligned |
| Severity | Critical business impact requires human SEV1 review; corroborated ordinary multi-user outage uses SEV2 | Count alone is insufficient |
| Notifications | L1 plus relevant service owner; conditional Infrastructure/Security; L1 coordinates incident lead | MOCK tool only |
| Runtime identifiers | Existing C article ID meanings are preserved; new IDs KB-025/KB-026 cover two additional diagnoses | Migration map supplied |
| Taxonomy | Use backend canonical domains/categories and owners; CERT_EXPIRED belongs to GRP-INFRA | Source-aligned |
| Retrieval | Orchestrate has not been uploaded/tested; all 56 current cases are NOT_RUN | Pending |

## Diagnostic and safety requirements

Symptoms shortlist candidates; they do not establish a diagnosis. Required evidence and exclusions must support the final decision. Ask discriminating questions and keep unsupported alternatives open. A populated question list does not prove each answer eliminates a candidate; scenario-level question quality still needs validation.

Security-sensitive, privileged-access and priority-1 tickets always require human handling. Article-specific human conditions also apply. False mandatory_human in a route is not an exemption. Ordinary HIGH-confidence specialist routing can assign directly; mandatory-human specialist assignment needs an approved admin review for the same ticket and group. Review approval never permits agent resolution of mandatory-human cases. MEDIUM routes to L1 with the specialist recommendation; LOW requires human triage.

Agent resolution requires a matching latest DIAGNOSED/HIGH/RESOLVE result, approved agent-resolvable article, matching TOOL_CHECK conditions, completed required step IDs, no specialist step and explicit user success confirmation. The simulated checks do not actually change accounts. Conditions and approval are enforced in structured backend records, not by PDF retrieval.

## Outages

Count only non-final, non-global, unlinked tickets in an inclusive UTC window. Filters use AND. Require exact category + CI + location and corroborating symptoms/service-health evidence. Check an existing matching open global first. Missing CI/location prevents global creation and requires human triage. Do not combine different sites, CIs or days.

The configured scopes are VPN/CI-VPN/LOC-A, Availability/CI-PORTAL/LOC-B and Availability/CI-ERP/LOC-C, each 3/30. Other scopes require investigation/human assessment. SEV1 and any new global with mandatory-human children initially belong to L1. Reusing an existing global does not overwrite its severity or owner; record any need for further review.

## Evidence and limitations

The source package was shaped from synthetic historical records; those outcomes are not evidence that a new ticket is resolved. No hidden evaluation answers were imported into knowledge. Original keyword smoke-test results are archived intact. New queries are development cases derived from articles, not independent evaluation evidence.

The backend source supports account status, application entitlement and service-health checks. Some article checks need human observations or future tools, including security-policy indicators not exposed by account status. Never infer missing evidence as FALSE or claim an unsupported check ran. Do not request or retain credentials; redact synthetic secret-like content in logs.

Backend schema and selected service behavior were checked locally; no running deployment was contacted. Freeze article IDs against the actual backend again before import. Strict import views omit authoring-only metadata; partial import files are not a complete replacement dataset. The backend policy model lacks approval status, so the owner must control policy activation separately.

# Review and approval of all 26 diagnostic articles

25 October 2026

The owner authorized: "check all and approve if they are ok". Every article was read individually. Required-evidence lists were rewritten as observable facts and source requirements; unsupported tool capabilities, overbroad exclusions and ambiguous operational authority were corrected before approval. All articles are now version 3.

**26/26 approved for scoped synthetic diagnostic guidance. Only KB-001 is an agent-resolution candidate.** The remaining 25 have agent_resolvable=false. Security, privileged-access and specialist workflows remain human-led.

| Article | Diagnosis/classification | Approved use and review finding |
|---|---|---|
| KB-001 | PASSWORD_EXPIRED | Account expiry evidence, fresh sign-in/cached-session distinction and MFA-lock exclusion; conditional guided self-service. |
| KB-002 | ACCOUNT_LOCKED | Lock state is measurable; ordinary versus security-policy lock reason requires authorized human evidence. |
| KB-003 | MFA_FAILURE | Separate MFA-stage symptoms from password failure; registration/push causes remain human-verified. |
| KB-004 | MISSING_ENTITLEMENT | Exact application entitlement/provisioning evidence; no access grant from chat or retrieval. |
| KB-005 | APP_AUTH_FAILURE | Compare account, entitlement and app-specific errors; avoid treating cached sessions as fresh authentication. |
| KB-006 | LOCAL_ENDPOINT | Device-isolated pattern does not identify a driver, OS or hardware component; endpoint checks are human-supplied. |
| KB-007 | APP_OUTAGE | Shared scope goes to Supervisor; monitor/count thresholds do not automatically confirm or exclude outage. |
| KB-008 | VPN_OUTAGE | Shared VPN screening, preserve conflicting health evidence; article approval does not activate global-incident policy. |
| KB-009 | PHISHING | Suspected phishing is immediately human-led; no unsafe content opening or verified-maliciousness claim. |
| KB-010 | PRIVILEGED_ACCESS | Classify elevated-access request and preserve actual approvals; no privileges granted by the agent. |
| KB-011 | SERVER_FAILURE | Infrastructure root cause needs measured/log evidence; exact CI and scope required. |
| KB-012 | UNKNOWN_ISSUE | Unknown remains INCONCLUSIVE with null diagnosis; collect scope without guessed service identifiers. |
| KB-013 | DNS_FAILURE | Distinguish name-resolution pattern from resolver/record/cache cause; DNS lookup is not an implemented tool. |
| KB-014 | WIFI_FAILURE | Separate peer and alternate-network observations; profile/adapter/access-point root cause remains unverified. |
| KB-015 | DISK_FULL | Require measured free space; no assumption that Downloads files are disposable and no deletion of business data. |
| KB-016 | PRINTER_OFFLINE | Reachability/power/queue observations remain distinct; no printer or queue-management tool is implied. |
| KB-017 | APP_ERROR | Capture reproducible action/error; application cause requires logs or safe reproduction. |
| KB-018 | SYNC_DELAY | Timestamped source/destination mismatch supports delay pattern, not an invented queue diagnosis. |
| KB-019 | MALWARE | Suspected compromise requires Security Operations; agent does not isolate or clean up the endpoint. |
| KB-020 | DATA_EXPOSURE | Minimum necessary exposure references only; security/privacy owners assess actual scope and notifications. |
| KB-021 | STORAGE_FAILURE | Shared storage versus local disk/permissions distinguished; exact service and authorized metrics needed. |
| KB-022 | CERT_EXPIRED | Expiry must be distinguished from chain/mismatch/clock issues; no bypassing validation or invented certificate check. |
| KB-023 | ACCOUNT_DISABLED | enabled=FALSE evidence retained even if lock/expiry coexist; human authorizes reactivation. |
| KB-024 | REQUEST_GUIDANCE | Approved for how-to classification and retrieval of a concrete procedure; agent_resolvable changed to false. |
| KB-025 | ACCOUNT_LOCKED_POLICY | Security-policy lock reason requires authorized security evidence; ordinary account tool cannot expose it. |
| KB-026 | VPN_CLIENT_ISSUE | Preserve exact local configuration versus credential errors and peer scope; shared impact returns to Supervisor. |

## Limits of this approval

Approval permits evidence-based diagnostic guidance, not automatic confirmation of a root cause. Unsupported checks require an authorized human or a separately implemented tool. User reports remain USER_RESPONSE; UNKNOWN results remain unknown. Specialist steps never become agent-executable merely because the article is approved.

KB-001 now also requires recorded mfa_locked=FALSE before its self-service path. Its human restrictions, evidence requirements, approved-portal identity verification, exact completed steps, user confirmation and backend success remain necessary. This review has not supplied a real portal URL, verified any user identity, changed credentials, executed a fix or resolved a ticket.

KB-024 had agent_resolvable=true without a concrete supported-platform runbook or machine-verifiable conditions. It is now approved only as classification/retrieval guidance and has agent_resolvable=false.

Article approval does not approve activation of the escalation policy, specialist routing, outage declarations or global-incident creation. policy_approved remains false. Outage articles now explicitly defer screening and policy decisions to the Supervisor/authorized humans.

## Verification and deployment

**174 tests passed.** The suite verifies article/version/hash approval integrity, specialist-resolution restrictions, and a separate draft fixture so draft guidance still cannot authorize resolution.

The approval register and full article set were updated locally. Per-article version, scope, changed fields, direct authorization and SHA256 are recorded in article_review_2026-10-25.json and the reviewed approval register. Earlier KB-001 approval is retained in approval history; this version-3 review supersedes its version-2 content.

**Not deployed:** the existing v6.2 ZIP, original knowledge PDFs and live backend registry are unchanged. The backend still has older definitions, step IDs and article coverage; compatibility must be verified before import. No new bundle was built by this review.

The full guided resolution workflow still needs the previously identified runtime/backend alignment and an end-to-end successful resolution test. Approval alone does not complete that implementation.

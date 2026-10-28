# Workstream A merge validation — 6 October 2026

The supplied JSON files were validated and imported into a separate operational profile. The PDF is a source specification, not an instruction to overwrite existing policy. Original files are archived unchanged under `evaluation/workstream_a`. SHA-256 hashes and counts are recorded in `validation_summary.json` there.

## Imported data

| Item | Count |
| --- | ---: |
| Existing historical tickets retained | 500 |
| New evaluation tickets | 134 |
| Matching offline ground-truth records | 134 |
| Total tickets in the new database | 634 |
| Normal / ambiguous / security / vague individual cases | 36 / 28 / 14 / 12 |
| Outage tickets: three clusters of eight | 24 |
| Decoy tickets: groups of eight, six, six | 20 |
| Added synthetic user / asset references | 134 / 98 |
| Declared account / entitlement / health fixture facts | 60 / 18 / 18 |

IDs are unique and ticket/label joins are exactly one-to-one. All foreign keys, schemas and timestamps pass import validation. Required fixture facts have no conflicting values. These facts were explicitly supplied in `required_fixtures`; expected diagnoses and scripted answers were not used to invent monitor or account results.

## Compatibility repairs completed

- Added `ACCOUNT_LOCKED_POLICY` to Authentication, routed to `GRP-SEC` with mandatory security handling. It is distinct from `ACCOUNT_LOCKED`.
- Added `VPN_CLIENT_ISSUE` to VPN, routed to `GRP-NET`. It is distinct from `VPN_OUTAGE`.
- Removed earlier importer aliases that incorrectly collapsed those distinctions. The new profile retains the original diagnosis codes in historical tickets.
- Added missing user/asset lookup records with neutral synthetic labels; their descriptive metadata was not supplied.
- Materialized the 96 declared fixture facts in operational files. Entitlement roles remain empty because role lists were not supplied.
- Kept the backend's seven canonical domains. Input aliases map Application to Applications, Endpoint to Endpoints, and Network/Other to Network or the category's canonical Infrastructure/Security domain. The PDF's four reporting buckets do not replace the seven-domain runtime contract. Share this mapping with A, B and D.
- Archived ground truth separately from operational data. It is excluded from API responses, OpenAPI tools and the Docker image. Initial tickets have no hidden diagnoses or answers.

## Items requiring team coordination

| Finding | Owner / required decision |
| --- | --- |
| No knowledge articles exist for `ACCOUNT_LOCKED_POLICY` and `VPN_CLIENT_ISSUE`. | B: author and approve diagnostic articles before evaluating knowledge-guided diagnosis for these codes. Routing and diagnosis storage are supported now. |
| Six decoy CI/location scopes have no configured outage threshold policy. | B: approve policy rows for VPN/CI-VPN/LOC-D; Availability/CI-PORTAL/LOC-A, LOC-C, LOC-D; Availability/CI-ERP/LOC-D, LOC-E. Numeric window checks pass, but do not treat that as full policy coverage. Existing configured scopes remain unchanged. |
| Sixteen mandatory human cases do not declare security/privileged flags at intake. | A/D: confirm intentional discoverable risk; D must identify the risk through evidence/questions and record the correct diagnosis. C applies security handling once established. No hidden labels were copied into initial flags. |
| PDF describes DECOY-2 as seven tickets, while both JSON files contain six. | A: correct the PDF or supply the missing ticket and matching label. Current import uses the consistent JSON pair. |
| Dataset has 134 rows, while the project target says 80–100 evaluation cases. | Lead/A: agree whether 90 individual cases plus six grouped scenarios count as 96 scenarios. Do not claim 134 rows satisfy an 80–100-row limit. |
| No companion taxonomy/groups JSON was supplied; two entries were reconstructed from the PDF. | A/B: ratify the two new codes and domain mapping in a shared versioned taxonomy. Existing seven resolver groups match. |
| Historical troubleshooting worklogs/evidence were not supplied with these files. | A/C: provide authored history observations and agree an import contract. These new evaluation files do not complete that historical-data requirement. |
| Role-specific entitlement checks lack role lists. | A/B: supply roles if those checks are part of the evaluation. Basic entitled/provisioning checks are supported. |
| TST-0001 initially suggests a whole row is affected, while a scripted follow-up says colleagues are healthy. | A: confirm deliberate noisy reporting or clarify the text. Authored text was preserved. |

The sixteen intake-risk cases are TST-0006, TST-0009, TST-0025, TST-0033, TST-0040, TST-0069, TST-0070, TST-0072, TST-0074, TST-0092, TST-0093, TST-0115, TST-0119, TST-0123, TST-0124 and TST-0131.

## Verification

All **91 automated tests passed**, including 13 new Workstream A integration tests. Tests used disposable databases and checked all 134 initial tickets, all declared diagnostic fixture values and retry behavior, taxonomy distinctions, hidden-label isolation, and all six eligible password resolutions.

Each outage was replayed at ticket arrival times: counts one/two do not create a global ticket, the third reaches the configured threshold, and later children link to the existing global ticket. Each outage has eight linked children. Decoy maximum counts in a 30-minute matching scope are respectively one, two and one, below a threshold of three. This temporal replay matters: querying everything at the final frozen clock is not the same test.

An upstream Starlette/httpx deprecation warning remains; no test failed. These are backend contract tests, not an end-to-end test of Workstream D's agent.

Live HTTP verification on port 8001 retrieved all 134 evaluation tickets as NEW with no diagnosis, retrieved HIS-0001, and loaded OpenAPI successfully. No live test changed ticket state.

## Local usage and preservation

The merged database is `work/workstream-a-api.db`; the previous database `work/local-api.db` was preserved. Port 8000 was already occupied by the old API, so the new profile was started on **http://127.0.0.1:8001/docs**. Existing service/admin keys still apply. Use ticket ID `TST-0001` in `get_ticket_details`, not as the API key.

From the workspace directory, restart the new profile with:

```powershell
& ./outputs/Start-Local.ps1 -Dataset workstream-a -Port 8001
```

To select the old profile explicitly, use `-Dataset starter`. The launcher now selects Workstream A automatically when its prepared profile exists. Do not run the generic starter smoke script against this profile: its assertions target the original INC fixtures. Use `tests/test_workstream_a.py` instead. Ground truth is for offline evaluation only; do not mount it into an agent's retrieval corpus.

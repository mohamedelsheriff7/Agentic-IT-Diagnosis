# Verification report

Verified locally on Windows, 2026-10-01, Python 3.12, using the exact versions in requirements.lock.

## Results

- **78 pytest tests passed** in 25.20 seconds on the final code/fixtures.
- **Real HTTP smoke passed**, with Uvicorn listening on 127.0.0.1:8765. Exercised health, 401 auth, seeded ticket read, create/retry, account observation, outage counting, /docs and denial of evaluation-file access.
- **All four demonstration flows passed over real HTTP**: confirmed password-expiry resolution; application specialist routing; Arabic clarification/human review; VPN global creation and later linking with mock notification.
- **OpenAPI validation passed**: genuine converted 3.0.3, JSON and YAML equivalent, exactly 17 unique required operation IDs, one HTTPS server, X-API-Key security, no admin/health operations or admin-only schemas. Full developer specification also exported.
- **Dataset scale test passed**: imported 500 historical plus 90 open records into SQLite. This synthetic expansion verifies capacity/schema support, not independent evaluation quality.
- Explicit authenticated import and reset commands were run successfully against the smoke database. Fixture generation was verified byte-for-byte reproducible under the same seed/clock.

## Test coverage

| Area | Verification |
|---|---|
| 17 tools | Successful tool paths plus complete four-flow integration test |
| Authentication | Missing/wrong service key; admin key required for review decisions |
| Inputs/IDs | Strict extra-field rejection, enums/ranges, unknown ticket/reference IDs, timezone-aware input |
| Audit/atomicity | Initial and automatic mutation logs; rollback on late evidence and global-child validation failures |
| Retries | Original response replay, conflicting inputs, diagnostic observation deduplication, persistence across app recreation |
| Resolution | Recorded diagnosis, HIGH/RESOLVE recommendation, matching approved article, required steps, real tool evidence, explicit user assertion, final-state rejection |
| Safety/reviews | Security/privileged/critical restrictions, requested versus approved, group-bound admin approvals, flags preserved, critical global triage |
| Routing | HIGH direct routing; MEDIUM L1 with specialist/alternatives; LOW pending human triage |
| Retrieval | History excludes open records; useful/no-match and Arabic examples; approved knowledge guidance |
| Evidence | Fixed account/entitlement/health states, UNKNOWN state, same-ticket references, future evidence rejection, secret redaction |
| Outages | All three clusters meet threshold; all three decoys fail; exact inclusive time boundary and UTC offsets; AND grouping; excludes linked/global/final tickets |
| Globals | Atomic creation/linking, duplicate reuse, concurrent creation serialization, duplicate-link audit suppression, self/non-global/inactive/conflicting/wrong-scope rejection |
| Isolation | No hidden evaluation fields in operational responses/database; strict import rejection of hidden fields; no static file endpoint |
| Import | Full rollback on bad replacement, strict schemas, deterministic fixtures, final-scale record counts |
| OpenAPI | Structural validation, operation/security/server assertions, real conversion, bad public URL rejection, admin exclusion |

One upstream deprecation warning remains: the pinned Starlette release deprecates its httpx-based TestClient path in favor of httpx2. Tests pass; no backend failure results. httpx remains the HTTP test dependency selected for this implementation.

## Reproduce

From the project root, install requirements.lock, then run `python -m pytest`. For HTTP checks, import fresh fixtures, start Uvicorn, set API_KEY and optional SMOKE_BASE_URL, then run `python -m scripts.smoke` followed by `python -m scripts.demo_flows`. For exports set PUBLIC_BASE_URL, then run `python -m scripts.export_openapi` and `python -m scripts.validate_openapi`.

## Not verified

Docker executable was unavailable, so the Dockerfile/Compose artifacts were not built or executed. No public HTTPS service or IBM tenant credentials were supplied. Orchestrate commands/UI guidance were checked against current official IBM documentation; actual tenant import, connection binding, network/TLS reachability and draft/live execution remain to be verified. The checked-in example HTTPS URL is not deployed. This is not a live Maximo integration or production security assessment.


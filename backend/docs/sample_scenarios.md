# Four demonstration flows

Start with a freshly imported dataset and the default frozen clock. These are explicit scripted integration examples, not a Diagnostic Agent, and they do not load evaluation answers. The real conversation agent must collect and supply user responses itself.

```powershell
$env:API_KEY = Read-Host 'Backend service key'
# Optional for a different local port:
# $env:SMOKE_BASE_URL = 'http://127.0.0.1:8765'
python -m scripts.demo_flows
```

The runner executes these sequences using actual HTTP and asserts their outcomes. Run once per reset. Requests have unique action IDs; saved examples in app/examples.py show the API shapes, with returned evidence/global IDs substituted by the runner.

1. **Ambiguous access — INC-1001.** Read the undecided ticket, ask whether other apps work, record the reported expiry message, check USR-001. The stored observation is enabled/unlocked/password-expired. Record PASSWORD_EXPIRED with KB-001 and HIGH confidence, then submit completed PASSWORD_EXPIRED-1 and explicit user confirmation. Expected: RESOLVED with timestamps and article link; never CLOSED. No actual password changes occur.
2. **Specialist application routing — INC-1005.** Check account, APP-PORTAL entitlement and CI-PORTAL/LOC-A service health. Those states are healthy while the description says the application fails. Explicitly record APP_AUTH_FAILURE/ROUTE and assign GRP-APP, preserving IAM as an alternative. Expected: QUEUED to Application Support with an assignment log. The backend does not infer this diagnosis itself.
3. **Vague Arabic — INC-1012.** Ask “ما هو التطبيق وما هي رسالة الخطأ؟”. Record INCONCLUSIVE/LOW/ASK_MORE with missing information. Request L1 investigation. Expected: diagnosis remains null, review REQUESTED, ticket PENDING. A request is not an approval.
4. **VPN burst.** Count VPN + CI-VPN + LOC-A in the inclusive 30-minute window: three tickets. Service health independently reports UNAVAILABLE. Create a SEV2 global for CLUSTER-1-1 and CLUSTER-1-2, then link CLUSTER-1-3 as the later-arriving report. Expected: one global incident, three unique children, zero remaining unlinked tickets in the count, and a MOCK notification. Repeating the same action returns the original result; a new create action for the same scope reuses the global.

Other isolated clusters are CI-PORTAL/LOC-B and CI-ERP/LOC-C, each with count 3. Decoy scopes CI-VPN/LOC-D, CI-PORTAL/LOC-E and CI-ERP/LOC-F each count 1: similar reports are either 90 minutes old or at LOC-G. See data/outage_fixtures.json and escalation_policy.json. All six scenarios are tested with frozen timestamps.

Mandatory-human examples: INC-1009 suspected phishing, INC-1010 privileged access, INC-1011 critical priority. Request review, then an administrator may approve specialist routing using X-Admin-Key at /admin/human-reviews/{review_id}/decision. No approval allows agent resolution of these cases.

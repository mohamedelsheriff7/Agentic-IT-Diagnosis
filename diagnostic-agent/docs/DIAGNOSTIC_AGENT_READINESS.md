# Diagnostic Agent v6.6 — delivery status

Historical v6.6 assessment. See [the current v6.7 patch and validation report](V67_REASONING_PATCH.md) for the latest implementation and remaining limits.

Reviewed 2026-10-26. Scope: the Python Diagnostic Agent, native LangGraph packaging, its backend adapter, bundled diagnostic knowledge and caller result. Supervisor assignment and global-incident creation belong to other agents.

**Status: a working, tested password-resolution path; broader diagnostic delivery readiness is not established.** The independent batch exposes both agent coverage gaps and substantial evaluator answer coverage limits. Passing implementation regressions is not a diagnostic accuracy claim.

## Gap status

| Delivery gap | Work completed | Remaining acceptance |
|---|---|---|
| Guided resolution | KB-001 exact step tracking, separate success confirmation, actual backend resolution, failed/uncertain paths stay open | Repeat the completed flow in the imported WXO version |
| Resolution/confidence gates | Recognized backend restrictions evaluated against ticket facts; expired-password HIGH uses recorded account evidence plus corroboration, without requiring a historical majority | Other diagnoses retain conservative legacy confidence logic; broader article-by-article calibration remains |
| Structured caller result | Contract 1.0 at graph root, assistant metadata and HTTP; schema and contract tests | Verify WXO Supervisor consumption in the tenant |
| Independent evaluation | 134 separate Workstream A records, original-language scripted answers, before/after reports, identified failures | Improve answer simulator coverage; address general diagnostic coverage; repeat with fresh human-reviewed cases |
| Delivery documentation | Current import guide, caller contract, local setup, verification commands and limits | Record final WXO import/Supervisor acceptance evidence |

## Implementation in this patch

- Removed the blanket rejection of KB-001 just because its restriction list was nonempty. Exact recognized restrictions are checked; unknown restriction text continues to require review.
- Added WAIT_STEP → WAIT_SUCCESS → RESOLVED progress. Step completion and original-problem success are separate assertions with recorded USER_RESPONSE evidence.
- Required all four backend account observations, approved matching guidance, corroborating user evidence and absence of mandatory restrictions for the password HIGH-confidence path. No LLM certainty is used.
- Kept backend KB-001 unchanged. Its exact `PASSWORD_EXPIRED-1` step and existing backend schema govern resolution.
- Stopped post-resolution mutation attempts. The backend's successful `resolve_ticket` response is the resolution event; RESOLVED/CLOSED tickets remain read-only.
- Exposed the structured result outside hidden message metadata. Evidence/trace from a different ticket is not copied into the active ticket's result.
- Added endpoint-topic retrieval filtering: generic connection/configuration words cannot introduce unrelated Bluetooth/camera/notification guides.
- Added mandatory handling for an explicit English report of credentials entered/shared on a fake or suspicious page, even with a missing intake flag. This narrow matcher does not establish comprehensive multilingual security detection.

## Verification evidence

| Check | Result |
|---|---|
| Regression suite | 203 passed |
| Packaged decision challenges | 18/18 passed |
| Extended packaged checks | 25/25 passed |
| Relocated single-file factory | Passed; no sibling diagnostic package required |
| Message-only continuation and async streaming | Passed in local verification |
| Bundled local self-service guide retrieval | 12/12 example scenarios retrieved |
| Real synthetic backend KB-001 resolution | Passed; see [the live report](v66_live_resolution_results.json) for exact ticket/result IDs and final package SHA256 |
| Final WXO import and Supervisor use | Not tested in this session |

The backend test creates a synthetic ticket, collects the simulated user's observations, presents the approved self-service step, records completion, separately confirms original sign-in success and verifies backend RESOLVED linked to KB-001. No real password or account is changed. It is a workflow test against synthetic fixtures, not evidence that a real user's credentials were repaired.

## Independent evaluation results

The same evaluator runs an older v6.5 ZIP and v6.6 against 134 separately authored Workstream A tickets. Gold labels are consumed by the evaluator only. The agent receives raw ticket fields, implemented tool fixtures and selected original-language user answers. Evaluation answers are excluded from the native package. Data/oracle hashes and per-ticket outputs are saved in [before](independent_evaluation_before.json) and [after](independent_evaluation_after.json).

| Measure | v6.5 | v6.6 |
|---|---:|---:|
| Confirmed diagnoses matching gold | 0/134 | 0/134 |
| Routing recommendation top 1 proxy | 58.96% | 58.96% |
| Routing recommendation top 3 proxy | 63.43% | 63.43% |
| Mandatory-human labelled cases escalated | 19/20 | 20/20 |
| Runtime errors | 0 | 0 |
| Questions matched to available answer topics | 56/378 | 57/368 |
| Resolution-ready cases | 0 | 0 |

Languages: English 67, Arabic 39, Franco-Arabic 28. No language group achieved a confirmed matching diagnosis in this batch. Most questions received the simulator's unknown answer because its topic matcher could not supply the available fact. Therefore **0/134 is the observed result of this limited harness, not a reliable estimate of real-user diagnostic accuracy**. The dataset/oracle were inspected during evaluator development; it is not an untouched holdout. Some oracle diagnoses also require evidence the oracle does not supply to answer the agent's stricter checks. Human review of those disagreements is needed.

No actual ticket resolutions were executed in this batch. Actual resolution rate and false-resolution rate are **not measured**, not zero. The separate live KB-001 test cannot establish a population-wide resolution rate. Routing scores are recommendation proxies based on canonical candidate groups; no assignments were executed.

### Five reviewed failure patterns

1. **TST-0014 — password.** Tool fixtures confirm expiry, but the available answer explains inability to get past laptop sign-in. The narrow answer interpreter does not connect that paraphrase to its outstanding other-applications question. Confirmation/corroboration is not reached. Work needed: contextual paraphrase handling without treating cached sessions as universal account proof.
2. **TST-0060 — locked account.** A vague intake becomes clearer in a later reported lock message. The engine does not adequately generate fresh hypotheses from new free-text evidence, so it can miss the appropriate account check. Work needed: candidate refresh driven by observed symptoms with provenance, not gold labels.
3. **TST-0044 — missing entitlement.** The application and empty-menu symptom emerge later, but do not reliably update the candidate/check selection. Work needed: gather usable application identity and refresh entitlement hypotheses, while retaining schema-valid backend identifiers.
4. **TST-0050 — DNS.** The oracle expects DNS failure, but does not provide the direct-IP comparison requested by the agent. Refusing to invent that comparison is appropriate. Work needed: distinguish evaluator evidence gaps from unnecessarily strict article criteria through manual adjudication.
5. **TST-0007 — VPN.** A peer-success paraphrase is not recognized reliably. Earlier retrieval also introduced irrelevant Bluetooth questions; v6.6 now excludes those unrelated guides. Work needed: contextual peer-answer interpretation and targeted follow-up rather than premature generic handoff.

Separately, **TST-0072** reports a password entered on a fake page while `security_sensitive=false`. The new reported-exposure safety check closes this observed missed mandatory handoff. It does not confirm PHISHING as a diagnosis.

## Local run and handover

Use Python 3.12 and the pinned `requirements.txt`. Create `.venv`, install dependencies, and put `DIAGNOSTIC_SERVICE_API_KEY` and `DIAGNOSTIC_BACKEND_API_KEY` in the project's private `.env`. Never paste either key into chat or the ZIP. Start `Start-Agent.ps1`; the default is `http://127.0.0.1:8080/docs`. Use one local API worker with the included session store.

For the same native graph over HTTP, call `POST /langgraph/chat` with the service key in `X-API-Key`, `mode=backend`, a stable `session_id` and `message="Investigate <synthetic ticket ID>"`. Subsequent messages answer the outstanding question. The backend is a separate service/database; local graph sessions use SQLite under `data/sessions` and backend worklogs hold resumable conversation checkpoints.

For WXO, import `dist/isys-diagnostic-langgraph-v6.6.zip` in a new preview and bind the team API-key connection with app ID `isys_it_backend`. No extra tools, knowledge upload or instruction paste is needed for this packaged implementation. See [the import guide](NATIVE_LANGGRAPH_IMPORT.md) and [the caller contract](DIAGNOSTIC_RESULT_CONTRACT.md).

Reproduce the offline checks from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-tmp-delivery-new
.\.venv\Scripts\python.exe scripts\build_langgraph_package.py
.\.venv\Scripts\python.exe scripts\verify_langgraph_package.py
.\.venv\Scripts\python.exe scripts\verify_v61_challenges.py --package dist/isys-diagnostic-langgraph-v6.6.zip --report docs/v66_challenge_results.json
.\.venv\Scripts\python.exe scripts\verify_v61_extended.py --package dist/isys-diagnostic-langgraph-v6.6.zip --report docs/v66_extended_results.json
.\.venv\Scripts\python.exe scripts\evaluate_independent_agent.py --package dist/isys-diagnostic-langgraph-v6.6.zip --output docs/independent_evaluation_after.json
```

The independent evaluator also requires the adjacent supplied `Workstream A` dataset. The optional `scripts/verify_v66_resolution.py` contacts the backend, creates a synthetic ticket and resolves it; it is not an offline check.

## Remaining delivery gate

The next work is diagnostic coverage: robust contextual answer interpretation, hypothesis refresh after new symptoms, evidence-based confidence criteria beyond the single password scenario, and a better reviewed evaluation dialogue. Do not bypass missing evidence, approve unknown backend articles or claim automatic endpoint repairs to improve scores. Validate those changes against fresh conversations and the safety regressions, then perform the tenant import and Supervisor contract acceptance. The current release is suitable for controlled prototype testing, not a claim that the full diagnostic brief has been met.

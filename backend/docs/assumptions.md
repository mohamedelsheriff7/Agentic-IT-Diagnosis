# Assumptions and limitations

- Empty initial repository; Project Description.txt was absent. The pasted requirements are the baseline. Only backend/data/specs/tests/docs were built.
- Python 3.12, FastAPI/Pydantic 2, SQLAlchemy and SQLite. requirements.lock pins the tested direct/transitive environment. Docker uses Python 3.12-slim; its base tag is not digest-pinned, and Docker execution remains unverified on this host.
- A fixed default demo clock makes scenarios reproducible. Leave DEMO_CLOCK empty for real UTC. Regenerate/reimport when shifting the demo date.
- Checks accept action_id because they persist evidence even though simulated accounts/services remain read-only. No mutation accepts arbitrary status or owner overrides.
- Unknown synthetic account state means UNKNOWN. A check for a different affected user is rejected to prevent unrelated evidence satisfying a resolution.
- This demo intentionally permits agent resolution only for the password-expiry self-service article. Other articles provide diagnosis/routing guidance and specialist steps. Workstream B can add safe, explicit machine-readable conditions through validated imports.
- Mandatory rules are a hard safety floor in app/policy.py. escalation_policy.json documents that floor and configurable outage thresholds; changing the JSON cannot weaken security/privilege/critical restrictions. Agents read the supplied policy file through their own configuration, not a backend policy tool.
- Article human-escalation labels document the fixed floor and uncertainty handling; arbitrary new executable policy syntax is not supported. Confidence and step completion remain caller assertions.
- Public HTTPS endpoint, tenant credentials and actual Maximo schema were not provided. The reserved example URL is never a claim of deployment. Tenant import/live execution and Docker run are pending.
- The Maximo document maps concepts, not exact MBO/OSLC attributes. CHANGE is represented as a ticket-class extension for this prototype; actual Maximo change management is not reproduced.
- Workstream A must author independent final-scale evaluation datasets. A generated 500/90 import test proves schema/storage support only, not evaluation quality.
- SQLite serializes writers and suits the demo workload. No pagination for full worklogs, migrations, rate limiting, production identity management, notification delivery, real monitoring, or internet lookup is included.
- Service keys/admin keys should differ. One shared admin key attributes decisions as ADMIN; production would need per-person identity, review expiry and stronger approval auditing.

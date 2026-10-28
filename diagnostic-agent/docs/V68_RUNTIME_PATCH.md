# v6.8: repeated-run runtime resource fix

Fixes the reported WXO failure: `No such file or directory: /tmp/isys-diagnostic-core-.../adk-project/knowledge/taxonomy.json`.

## Reproduced cause

The v6.7 entrypoint extracted its embedded bundle into a new `TemporaryDirectory` and imported a shared Python package named `diagnostic_agent`. A warm worker could retain those modules after the first entrypoint's temporary directory was cleaned up. Importing another entrypoint created a different directory but reused the old modules, whose file paths still pointed to the deleted directory. The newly introduced-hypothesis step then failed when reading taxonomy.json. The verifier reproduces this exact failure in v6.7 before checking the fix.

## Change

- Cache extracted immutable bundle files under a content-derived path, without a TemporaryDirectory finalizer tied to an entrypoint object's lifetime.
- Load the embedded core in a private namespace derived from the full bundle hash. A worker's cached `diagnostic_agent` from a different bundle is not used by the new factory.
- Verify/restore packaged resources at import, factory creation, request handling and action execution. Missing or corrupted immutable files are replaced atomically from the embedded archive.
- Preserve ordinary development imports and fresh-process CLI verification aliases. A later version does not replace another version's canonical module aliases.
- Keep a short extraction path for Windows compatibility; account for a concurrent loader already restoring an identical file.

This is a packaging/runtime patch. Diagnostic rules, backend resolution conditions, KB articles, connection IDs and contract 1.0 are unchanged. The cache stores packaged code/knowledge, not conversation state or credentials. Backend checkpoints remain the conversation recovery mechanism.

## Validation

- Full regression suite: 235 passed, including the new warm-runtime failure regression.
- Exact v6.7 taxonomy failure reproduced; v6.8 passed five cleanup/reload/conversation cycles with old canonical modules still loaded.
- Garbage collection of repeated entrypoint objects did not delete resources used by the existing graph.
- Corrupt taxonomy restored; eight concurrent factory creations passed.
- Relocated single-file import, message-only continuation, async streaming and 12-guide retrieval checks passed.
- All 15 controlled native conversations passed across the five diagnosis scenarios and three input languages.

Reports: [runtime](v68_runtime_results.json) and [conversations](v68_dialogue_results.json). The runtime and conversation reports identify the tested ZIP by SHA256. No WXO tenant import was performed in this session. The existing broader diagnosis-coverage and entitlement-identifier mapping limits remain open; this patch does not claim to fix them.

Reproduce from the project root:

```powershell
.\.venv\Scripts\python.exe scripts\build_langgraph_package.py
.\.venv\Scripts\python.exe scripts\verify_v68_runtime.py
.\.venv\Scripts\python.exe scripts\verify_langgraph_package.py
.\.venv\Scripts\python.exe scripts\verify_v67_dialogues.py --package dist/isys-diagnostic-langgraph-v6.8.zip --report docs/v68_dialogue_results.json
```

The runtime regression needs both retained v6.7 and current v6.8 ZIPs to prove the original failure and mixed-version worker isolation. Its deletion simulation is restricted to its own owned temporary test cache.

## Retry in WXO

1. Import `dist/isys-diagnostic-langgraph-v6.8.zip` as ISYS Diagnostic Agent v6.8; select the existing `isys_it_backend` team connection.
2. Use a new preview conversation. Investigate the failed ticket by its exact ID. If its backend checkpoint can be restored, the agent should continue from the outstanding question; do not assume the failed turn recorded no work before crashing.
3. For a clean comparison, create a fresh ticket with the same manual-test helper/case. Do not reuse a resolved ticket as a new diagnosis test.
4. Repeat the test several times with fresh tickets, including starting another preview conversation and investigating the same unfinished ticket. Report any recurrence with the version, case number, exact ticket ID and full error text.

The available password article still lacks a real approved portal/procedure. Synthetic confirmation can test the prototype's resolution mechanics; it does not establish that a real password-change procedure was supplied or performed.

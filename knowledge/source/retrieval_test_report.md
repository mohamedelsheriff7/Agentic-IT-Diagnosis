# Workstream B retrieval validation report

Revision: 15 October 2026. Current status: NOT_RUN. Orchestrate knowledge has not yet been uploaded or tested.

## Current validation plan

retrieval_test_log.json and retrieval_test_log.csv contain the same 56 cases: 26 English, 26 Arabic and four Franco-Arabic queries. All 26 diagnoses are represented and expected article IDs match the revised articles. Actual returned IDs are empty, actual diagnosis is null/blank, and every result is NOT_RUN. Current executed count: 0; a pass rate is not available.

These cases were authored from the diagnostic articles as development checks. They do not establish independent test-set accuracy, language parity or question quality. Four Franco-Arabic cases provide initial coverage only.

## Preserved historical results

archive/original_delivery_before_alignment_2026-10-15/ contains the original JSON/CSV logs and report unchanged. Those logs reported 25/25 PASS using deterministic keyword matching over curated cues. They did not exercise Orchestrate, embeddings or a live retrieval service; queries were English-only and covered 25 of the 26 diagnoses. Original article IDs are preserved as observed; translate expected references using article_id_migration.json when creating new runs, never relabel old returned IDs as new observations.

## Execution and scoring

1. Use a controlled review/test knowledge setup and preserve the unapproved state. Owner content approval is a separate decision. Backend knowledge search returns approved articles only; do not flip approval solely to obtain test results.
2. Upload the three PDFs to their relevant agents and check actual extracted English and Arabic text.
3. Run each query through the actual configured retriever. Record actual ranked article IDs, retriever/version, timestamp and observed score where available.
4. Record PASS when the intended diagnostic article ranks first; otherwise FAIL and retain the actual result. Empty retrieval is FAIL for an executed positive case, never NOT_RUN. Record top-three presence separately.
5. Add independent Arabic/Franco-Arabic paraphrases, typos, ambiguous/negative cases and competing diagnoses before claiming project-level quality. Check routing/policy retrieval separately and verify outage decoys through agent/tools, not retrieval alone.
6. Summarize executed, passed, failed and not-run counts separately. Investigate misses; do not alter expectations simply to match output.

## Outstanding validation

No live retrieval failures or successes have been observed yet. Backend schema/service checks are reported in backend_validation.json; they are compatibility/safety evidence, not retrieval-quality evidence. Approval, live integration, independent multilingual evaluation and actual Orchestrate retrieval remain pending.

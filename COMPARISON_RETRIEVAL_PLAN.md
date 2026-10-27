# Shared comparison retrieval implementation plan

**Goal:** Remove repeated question embedding within a single multi-source comparison while retaining independent source recall and fallback.

**Architecture:** `comparison_service` owns one embedding task and runs per-source `prepare_evidence` calls concurrently. `scoped_chat_service`, `graph_search` and `search_service` pass the task to the dense path; sparse and graph paths remain independently authorized. The owner cancels and drains the task on every exit.

**Tech stack:** Python 3.12 asyncio, FastAPI, PostgreSQL/pgvector, Neo4j, pytest.

1. In `tests/test_comparison.py`, add a failing test with two source calls that cannot complete until both start and must await the same one-shot embedding task. Assert input order and citation indices. Add cleanup/cancellation and shared failure regressions.
2. Thread an optional shared task through `prepare_evidence`, `retrieve_version_evidence`, and `hybrid_search_versions`. Await it with `asyncio.shield` in the dense path; do not change ordinary single-source call sites. Use `asyncio.gather` with results in source order, propagate failures, cancel and await the owned task in `finally`.
3. Run focused unit and isolated database/Neo4j integration tests, including source isolation and degraded routes. Use the fixed development conflict samples and the real local embedding model to compare old/new multiple-source retrieval, disclosing sample count and timing scope.
4. Run required quality gates, review diff and commit only related files. Do not modify user data or use sealed cases for tuning.

# Retrieval resilience and measurement implementation plan

**Goal:** Preserve authorized keyword results when embeddings fail, reduce evidence lookup round trips, and measure actual retrieval without claiming fixture results as model quality.

**Architecture:** Keep existing source/version authorization predicates and RRF scoring. Run sparse and dense retrieval independently; only return an empty result when all applicable routes completed successfully. Resolve all candidate documents in one query and validate their revision identities. Run measurements against the isolated test database and the fixed development split.

**Tech stack:** Python 3.12, FastAPI, async SQLAlchemy, PostgreSQL/pgvector, pytest, Neo4j.

## Task 1: Independent search routes

Files: `packages/backend/app/services/search_service.py`, `packages/backend/tests/test_rag.py`, `packages/backend/tests/integration/test_graph_search.py`.

- [ ] Add a failing test where `encode_texts` raises and a permitted keyword match exists; assert the match is returned. Add failure/no-hit and normal empty tests; assert database queries retain owner and version filters. Add a synchronization test proving the sparse query begins before a blocked embedding finishes.
- [ ] Run `python -m pytest tests/test_rag.py -q` under `.venv312`; confirm the new behavior fails on the existing implementation.
- [ ] Split the scoped dense and sparse paths into separate async operations using separate sessions. Await them together, preserve RRF ranks and `dense_weight`, return available matches on partial failure, and raise a sanitized error when a failed path plus empty alternatives cannot establish absence of evidence. Do not swallow cancellation.
- [ ] Re-run unit tests and isolated PostgreSQL authorization tests. Commit only this task's files.

## Task 2: Batch evidence document lookup

Files: `packages/backend/app/services/scoped_chat_service.py`, `packages/backend/tests/test_scoped_citations.py`.

- [ ] Add a failing test with two candidates and one unavailable or mismatched document; verify one query and no evidence for an invalid document. Preserve the ranking and indices used in the prompt.
- [ ] Run `python -m pytest tests/test_scoped_citations.py -q`; confirm failure before implementation.
- [ ] Select all referenced `SourceDocument` IDs once; map by ID and only accept rows whose `revision_id` matches the candidate. Preserve source/version matching and quote data.
- [ ] Re-run focused tests plus existing scoped chat integration tests. Commit the task separately.

## Task 3: Reproducible retrieval measurements

Files: `packages/backend/evaluation/README.md`, `packages/backend/tools/` and focused evaluation tests.

- [ ] Inspect the fixed dataset schema and existing production ingestion APIs. Add a test that rejects non-local or incorrectly named databases and records `not_run` when a real embedding model is unavailable. Never substitute a fake model under a production label.
- [ ] Implement a bounded development-split runner using synthetic source assets and isolated PostgreSQL. Capture dataset hash, commit, actual model identity, per-case retrieved source/version/quote, timing, and errors without credentials or private data. Do not touch the sealed split for calibration.
- [ ] Run the runner if the actual embedding model is locally available; otherwise document the blocker. Report Recall@5/MRR and p50/p95 only for completed real observations, with denominators.

## Verification

- [ ] Run frontend test/lint/typecheck/build, backend pytest/Ruff/Mypy, migration SQL and Compose config as required by project rules. State integration skips and real-model limitations precisely.
- [ ] Review `git diff --check`, preserve pre-existing user edits, and commit the verified changes.

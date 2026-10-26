# Neo4j Graph Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute inline in this workspace; do not delegate.

**Goal:** Add recoverable Neo4j entity/relationship projection for published sources and use it beside the existing pgvector/keyword retrieval while preserving source-version citations.

**Architecture:** PostgreSQL remains the authoritative store and owns durable graph-build state. A worker extracts bounded, quote-validated relationship candidates from a published revision and writes a versioned Neo4j projection. Scoped RAG runs vector/keyword and graph lookups concurrently, resolves candidate chunk IDs through PostgreSQL ownership/version filters, merges them, and falls back when either route is unavailable.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, arq, Neo4j async Python driver, PostgreSQL/pgvector, Redis, Vue 3/TypeScript, pytest, Vitest, Docker Compose.

---

## File map

- `packages/backend/app/models/graph_task.py` and a new Alembic revision: persistent per-revision build state, lease, active build ID, counts and errors.
- `packages/backend/app/services/graph_extraction.py`: LLM JSON parsing and exact quote validation; no database access.
- `packages/backend/app/services/graph_store.py`: Neo4j connection, schema, idempotent projection writes, bounded candidate reads and cleanup.
- `packages/backend/app/services/graph_jobs.py`: claim/recover/build/retry state machine and publication hook.
- `packages/backend/app/services/graph_search.py`: two-route orchestration, PostgreSQL verification and rank fusion.
- `packages/backend/app/api/graph_api.py`: owner-scoped status and retry endpoints.
- `packages/backend/app/services/source_publication.py`, `source_jobs.py`, `image_source_jobs.py`, `source_cleanup.py`, `worker.py`, `scoped_chat_service.py`, `main.py`: narrow integration points.
- `packages/shared/src/types/source.ts`, `packages/consumer/src/api/sources.ts`, `packages/consumer/src/views/sources/SourceWorkspace.vue`: status and retry UI.
- `docker-compose.yml`, `compose.test.yml`, `packages/backend/.env.example`, dependency inputs/locks, `.github/workflows/ci.yml`, `README.md`, `TESTING.md`: service and verification contract.

## Shared contracts to keep task boundaries stable

Use these signatures as the cross-file contract. The task steps below may add private helpers but must preserve the named inputs/outputs.

```python
@dataclass(frozen=True)
class GraphCandidate:
    item_id: str
    source_id: str
    revision_id: str
    build_id: str
    route_rank: int

async def extract_relations(chunks: list[KnowledgeItem]) -> list[ExtractedRelation]: ...
async def write_projection(build_id: str, user_id: str, source_id: str,
                           revision_id: str, relations: list[ExtractedRelation]) -> None: ...
async def find_candidate_chunk_ids(user_id: str, revision_builds: dict[str, str],
                                   question: str, limit: int) -> list[GraphCandidate]: ...
async def retrieve_version_evidence(versions: dict[str, str], question: str,
                                    user_id: str, top_k: int = 5) -> list[SearchResult]: ...
```

`ExtractedRelation` is a validated immutable value with `subject`, `predicate`, `object`, `quote`, `item_id`, `quote_start`, `quote_end`, and optional aliases. `revision_builds` maps revision ID to the single active build ID found in PostgreSQL. `GraphCandidate.item_id` identifies a `KnowledgeItem` and is never trusted until reloaded with owner/version predicates.

## Task 1: State model and isolated service contract

**Files:** Create `packages/backend/app/models/graph_task.py`, `packages/backend/app/migrations/versions/20261026_graph_tasks.py`; modify `packages/backend/app/models/__init__.py`, both Compose files, backend dependency inputs/locks and environment example. Test `packages/backend/tests/test_graph_task.py` and `packages/backend/tests/integration/test_graph_task.py`.

- [ ] Write a failing model test that asserts a unique `(revision_id, extractor_version)` key, a nullable `active_build_id`, and `pending` default. Run `python -m pytest tests/test_graph_task.py -q`; expect failure because `GraphBuildTask` does not exist.
- [ ] Add the model and migration with these concrete fields: `id`, `source_id`, `revision_id`, `user_id`, `extractor_version`, `status`, `active_build_id`, `lease_until`, `attempts`, `relation_count`, `rejected_count`, `error_code`, timestamps. Define `UniqueConstraint("revision_id", "extractor_version", name="uq_graph_revision_extractor")`; indexes on `status/lease_until` and `source_id`. Downgrade must reject nonempty graph task history.
- [ ] Add a Neo4j service pinned to a verified compatible image, localhost Bolt binding and named production volume; add an independent tmpfs Neo4j service and distinct localhost port to `compose.test.yml`. Add `neo4j` driver to input and both lock files. Add `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `GRAPH_EXTRACTOR_VERSION`, `TEST_NEO4J_URI` examples without live secrets. The test fixture must reject anything other than the dedicated localhost test port before a write.
- [ ] Run the isolated migration test and `docker compose config --quiet` plus `docker compose -f compose.test.yml config --quiet`; expect pass. Commit this task only after reviewing the staged diff.

## Task 2: Exact-evidence extraction

**Files:** Create `packages/backend/app/services/graph_extraction.py`; test `packages/backend/tests/test_graph_extraction.py`.

- [ ] Write failing tests with a synthetic chunk such as `"甲公司收购了乙公司。"`: accept `{subject:"甲公司", predicate:"收购", object:"乙公司", quote:"甲公司收购了乙公司。"}` and reject a fabricated quote, missing subject, oversized field or unknown chunk ID. A valid empty `relations` array yields an empty projection; all invalid entries from nonempty content raise a typed extraction error. Run the targeted pytest; expect import failure.
- [ ] Implement strict Pydantic response models, bounded field lengths/counts, Unicode normalization for lookup only, exact `quote in chunk.content` validation, and stable IDs derived from revision/chunk/offset/relationship content. Use existing OpenAI-compatible LLM configuration with a data-only prompt and JSON response; preserve per-chunk `origin` so OCR, corrections and manual descriptions remain distinct. Do not log body text.
- [ ] Test timeout, malformed JSON, no configured LLM, partial valid entries and no-text image cases. Run pytest, Ruff and Mypy for the new module; expect pass. Commit.

## Task 3: Neo4j projection adapter

**Files:** Create `packages/backend/app/services/graph_store.py`; test `packages/backend/tests/test_graph_store.py` and `packages/backend/tests/integration/test_graph_store.py`.

- [ ] Write failing tests for idempotent write, strict tenant/build filtering, query parameterization, no stored source body/path, duplicate relation suppression, and interrupted build invisibility. Real-driver tests require only `TEST_NEO4J_URI` pointing to the isolated Neo4j service; otherwise skip with an explicit reason.
- [ ] Create a singleton async driver with bounded connection and query timeouts; close it in backend/worker shutdown. Install named uniqueness constraints with `IF NOT EXISTS`. Use fixed labels and relationship types, parameterized entity/predicate properties, and `MERGE` keys. Build each new `build_id` without changing the active PostgreSQL pointer. `find_candidate_chunk_ids(user_id, revision_builds, query, limit)` returns only IDs/route metadata; no text.
- [ ] Add idempotent deletion of a build or source projection after PostgreSQL has hidden a deleted source. Run the adapter tests against the isolated container and repeat the write test to prove idempotence. Commit.

## Task 4: Durable publication jobs

**Files:** Create `packages/backend/app/services/graph_jobs.py`; modify `source_publication.py`, `source_jobs.py`, `image_source_jobs.py`, `source_cleanup.py`, `worker.py`; test `packages/backend/tests/test_graph_jobs.py`, `packages/backend/tests/integration/test_graph_jobs.py`.

- [ ] Write failing tests that one publication transaction creates one task, repeated publication/retry does not duplicate it, an unavailable LLM/Neo4j marks only graph indexing failed, and the source remains published. Test stale lease recovery and version rebuild without changing `current_revision_id`.
- [ ] Insert/get the graph task in `publish_revision` in its current SQL transaction, then enqueue after commit or let the existing maintenance tick recover `pending` rows. Worker claims one task with a lease, extracts every eligible chunk within an explicit documented budget, writes an isolated `build_id`, and switches `active_build_id` only after successful Neo4j commit. On error retain old pointer and store a safe error code. Retry resets failed state; leases recover crashes. Repeated publication of an already built revision reuses the task.
- [ ] Ensure image, document and repository publication paths all use this hook. On deletion, PostgreSQL authorization blocks candidates immediately and maintenance retries Neo4j cleanup. Run task tests and existing source/image lifecycle tests. Commit.

## Task 5: Dual-route evidence retrieval

**Files:** Create `packages/backend/app/services/graph_search.py`; modify `packages/backend/app/services/scoped_chat_service.py`; test `packages/backend/tests/test_graph_search.py`, `packages/backend/tests/integration/test_graph_search.py`.

- [ ] Write failing tests where a graph-only synthetic relationship returns a chunk absent from vector results, while a cross-user chunk, old revision and deleted source return nothing. Test vector route failure with valid graph evidence, graph timeout with valid vector evidence, both empty yielding `INSUFFICIENT`, and both failed yielding a service error.
- [ ] Start both retrieval coroutines concurrently with bounded timeouts. Select only completed `GraphBuildTask.active_build_id` rows for the request's version map. For every graph chunk ID, query PostgreSQL with `Source.user_id`, selected `(source_id, revision_id)`, ready revision, available item, and undeleted/unarchived source predicates. Merge deduplicated rows by stable route rank, cap per-source and total counts, and reuse `prepare_evidence`'s existing citation construction. Do not expose rank as confidence.
- [ ] Run scoped chat, comparison and Wiki tests, because they share `prepare_evidence`. Confirm saved citations still use PostgreSQL source/revision/document/locator. Commit.

## Task 6: Owner API and UI

**Files:** Create `packages/backend/app/api/graph_api.py`; modify `packages/backend/app/main.py`, `packages/shared/src/types/source.ts`, `packages/consumer/src/api/sources.ts`, `packages/consumer/src/views/sources/SourceWorkspace.vue`; test `packages/backend/tests/test_graph_api.py` and consumer component/API tests.

- [ ] Write failing API tests: owner reads status and retries only a failed task; another user sees 404; pending/processing/completed retry gives 409; source without publication returns a clear empty state. Write a UI test for status text and retry visibility; expect failure.
- [ ] Add `GET /api/sources/{source_id}/graph` and `POST /api/sources/{source_id}/graph/retry`; return typed `revision_id`, `status`, counts and safe error code, never raw model output. Add the shared type/client functions and a small source-workspace status area that refreshes after source publication and offers retry on failure. Guard late responses on source selection using the existing request-scope pattern.
- [ ] Run API/component tests and front-end typecheck/lint. Commit.

## Task 7: Isolation, CI and delivery

**Files:** Modify `.github/workflows/ci.yml`, `README.md`, `TESTING.md`, `NEO4J_DESIGN.md` only if a verified implementation decision differs; tests under `packages/backend/tests/integration` and consumer tests.

- [ ] Add a Neo4j CI service with a test-only password and explicit `TEST_NEO4J_URI`. CI must run real graph integration tests, not silently skip. Add a test that fails when the integration fixture sees a non-test database endpoint.
- [ ] Run the new end-to-end synthetic case on isolated PostgreSQL/Redis/Neo4j: publish, extract with deterministic LLM, graph-only relation recall, cite exact source version, republish and reject old graph evidence, then force Neo4j failure and verify vector fallback. Record exact commands/results without private content.
- [ ] Run `pnpm test`, `pnpm lint`, `pnpm typecheck`, both builds, backend pytest, Ruff, Mypy, Alembic offline SQL, both Compose checks. Fix new failures. Review `git diff`, commit remaining verified documentation, and push normally only if the task's existing remote and branch workflow permits it; follow CI before claiming remote success.

## Plan self-check

This plan maps every design requirement to a task: durable jobs (1, 4), quote-validated extraction (2), isolated graph projection (3), parallel retrieval and evidence authorization (5), user status/retry (6), failure isolation and real graph testing (4, 5, 7). No production migration, business data backfill, deployment or model quality claim is implicit. Keep the existing untracked `diagram/` files untouched.

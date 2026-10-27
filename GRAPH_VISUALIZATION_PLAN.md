# Authorized graph visualization implementation plan

**Goal:** Let a source owner inspect bounded, source-backed relation candidates from the current published graph build.

**Architecture:** Neo4j returns bounded relation pointers and entity labels; a dedicated backend service revalidates current ownership, build, source/document version, offsets and original text in PostgreSQL. A Vue panel renders distinct mention pairs and offers an accessible relation list and original evidence.

**Tech stack:** FastAPI, async Neo4j 5, PostgreSQL, Vue 3, TypeScript, SVG, pytest, Playwright.

1. Add failing real Neo4j/PG integration tests using a synthetic graph projection: current owner can see a verified quote, another user and old build cannot, bad offsets are rejected, and a changed publication/build during retrieval fails closed. Run them with the isolated test services and observe failure.
2. Add `list_projection_relations` to `graph_store.py` with parameterized Cypher, build and user scope and a bounded limit. Add a focused service to revalidate the returned pointers in PostgreSQL, and expose the authenticated source graph relations endpoint. Test unavailable, not-ready and truncation states.
3. Add shared response types and a consumer API method. Implement a lazy source graph panel with SVG relation pairs, a keyboard-accessible list, selected original quote and original download; guard late responses with request scope and account/source changes.
4. Add a browser fixture test for lazy load, quote selection, graph errors, source change and mobile sizing; inspect a screenshot. Run focused backend/frontend checks.
5. Run all project quality gates, document limits and commit only this task's files; preserve existing user edits.

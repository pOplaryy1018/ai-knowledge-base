# Source history and rollback implementation plan

**Goal:** Show published source history and safely republish a previously published immutable revision.

**Architecture:** Expose publication records and a locked, owner-authorized rollback endpoint; reuse the existing publication/event pipeline. The user interface sends the observed current publication ID to prevent stale updates. No schema migration.

**Tech stack:** FastAPI, async SQLAlchemy, PostgreSQL, Vue 3, TypeScript, Arco, pytest, Playwright.

1. Add isolated integration tests to `packages/backend/tests/integration/test_evidence_lifecycle.py`: upload and publish A then B, fetch history, roll back A with B's publication ID, assert A→B→A and a new change event; stale B ID must return 409, cross-owner/source, current target and missing original must fail without moving the head. Run tests and observe the missing endpoint failure.
2. Modify `app/api/source_api.py` and `app/schemas/source.py`: expose the current publication ID and history; validate owner, target, original and expected head under lock; call `publish_revision`, commit and return the source. Run the integration tests with `TEST_DATABASE_URL` pointing to the isolated database.
3. Add shared publication type and API functions in `packages/shared/src/types/source.ts` and `packages/consumer/src/api/sources.ts`. Add a publication history panel in `SourceWorkspace.vue`, with confirmation, busy/error states, and guarded refresh after source/identity changes. Use existing tactical styling and retain original preview actions.
4. Add browser/API regression coverage for history rendering, cancel, success, stale conflict and source switch; run focused frontend tests and browser checks using synthetic fixtures.
5. Run full project quality gates, inspect diff and preserve unrelated user edits; document current limitations and commit the independently verified feature.

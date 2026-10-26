# 双端战术档案界面 Implementation Plan

> **For agentic workers:** Inline execution in this session. The user explicitly waived further approvals. Follow `FRONTEND_REDESIGN_DESIGN.md` and preserve unrelated edits.

**Goal:** Deliver the approved black violet design across every admin and consumer route, major dialogs, and a persistent Q style 韬韬 knowledge assistant.

**Architecture:** Both Vue apps keep their routes, Arco components, APIs and business state. A shared token layer and targeted page shell styles provide the new visual language. The assistant uses the current scoped chat API with published source selection and source version citations; local private artwork is optional and ignored by Git.

**Tech Stack:** Vue 3, strict TypeScript, Pinia, Arco Design Vue, Vite, Vitest, existing FastAPI endpoints.

---

## File map

- `packages/{consumer,admin}/src/styles/global.css`: shared token vocabulary, Arco component skin and default states.
- `packages/{consumer,admin}/src/views/{Layout,Login}.vue`, `packages/consumer/src/views/Register.vue`: navigation, shell, authentication visuals.
- Existing views and dialogs under `packages/{consumer,admin}/src/views`: local spacing and information hierarchy where global tokens are insufficient.
- `packages/shared/src/utils/assistant-scope.ts`: pure rules for selecting published sources and respecting 100 source cap.
- `packages/shared/src/utils/assistant-scope.test.ts`: scope and reset unit tests.
- `packages/{consumer,admin}/src/components/TaotaoAssistant.vue`: app integrated persistent assistant; same UI contract, app specific API adapters.
- `packages/admin/src/api/{sources,scoped-chat}.ts`: use existing source and scoped chat backend endpoints with admin auth client.
- `.gitignore`: ignore local theme asset folders; public fallback remains CSS based.

## Task 1: Establish visual tokens and Arco skin

- [ ] Add `--akb-bg`, `--akb-surface`, `--akb-surface-raised`, `--akb-line`, `--akb-text`, `--akb-text-secondary`, `--akb-primary` and state colors to both global styles, using the spec hex values.
- [ ] Map existing consumer `--color-*` names and Arco `--color-*` variables to these values. Style Arco buttons, inputs, tables, tabs, modals, drawers, alerts, pagination and empty states without changing their API behavior.
- [ ] Run `pnpm typecheck` and `pnpm build:consumer && pnpm build:admin`; expected: commands exit 0 and no missing CSS assets.

## Task 2: Rebuild both app shells and auth pages

- [ ] Update both `Layout.vue` files and admin sidebar/topbar components to show grouped navigation, breadcrumb, responsive content and a persistent assistant mount.
- [ ] Update both `Login.vue` and consumer `Register.vue` with the two panel tactical composition, accessible labels, focus and error text. The artwork uses a local optional URL and a complete CSS fallback.
- [ ] Preserve all existing routes, redirects, login validation and logout behavior. Check at desktop and 390 px width.

## Task 3: Apply the system to every page and principal dialog

- [ ] Style user routes: knowledge base list/detail, sources, both chats, saved answers/detail/review, Wiki workbench/detail. Preserve source and answer version labels and exact status wording.
- [ ] Style admin routes: dashboard, users, knowledge bases, agents, files, statistics. Keep existing table columns and chart data binding.
- [ ] Style knowledge base, import, user and Agent dialogs plus file preview, import progress, source operations and Wiki/review decisions. Check empty, loading, error and narrow layouts.
- [ ] Run `pnpm lint`, `pnpm typecheck` and both builds; expected: exit 0.

## Task 4: Add the Q style 韬韬 assistant

- [ ] Add a failing test for published-source filtering, source-cap behavior and scope-change session reset in `assistant-scope.test.ts`.
- [ ] Run `pnpm test`; expected: new test fails before implementation.
- [ ] Implement the pure source rules, then run `pnpm test`; expected: new tests pass.
- [ ] Add an authenticated assistant to both layouts. Load accessible sources, show selected scope, send via `/api/chat/scoped`, stream text and citations, abort on logout/scope change, retain a session while collapsed, and show empty/error/no-evidence states.
- [ ] Keep Q sprites in ignored local asset folders; render an original CSS avatar when absent. Do not include copyrighted game assets in tracked code.
- [ ] Browser test open/close, conversation, source selection, keyboard Escape, mobile layout and logout. Backend still enforces source ownership.

## Task 5: Verify and package

- [ ] Run `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm build:consumer`, `pnpm build:admin`.
- [ ] Run backend pytest, Ruff, Mypy, migration SQL and Compose checks required by `TESTING.md`; disclose skipped real database checks.
- [ ] Inspect Git diff and tracked assets. No `.env`, user private artwork, game assets or unrelated existing edits in commits.
- [ ] Save browser screenshots of auth, sources, review, Wiki, admin table, assistant and modal at desktop and mobile sizes; report any fidelity gaps.

# Testing KnowBuddy

**For:** anyone checking that a change works, before a pull request or before submitting.
**You'll:** run the automated tests, then check by hand what they can't cover.
**Not here:** running the app → [RUNNING.md](RUNNING.md) · how to write tests (naming, fake data, security tests) →
[CONTRIBUTING.md](../CONTRIBUTING.md) §8.

**Contents:** 1. Backend tests · 2. Frontend checks · 3. Security invariants · 4. Manual checks · 5. Accessibility ·
6. Mock mode · 7. Before a pull request, before submitting · 8. When tests go wrong · 9. Not covered yet

## 1. Backend tests

pytest, in `backend/tests/`. Run them in Docker from the repository root (no local Python needed). The database
service must be running (`docker compose up -d db`):

```bash
docker compose run --rm --build --user root -e POSTGRES_DB=brain_test -v ./backend/tests:/app/tests backend sh -c "uv sync --locked --group dev --quiet && pytest -q"
```

✅ All pass (203 on 8 Oct).

- Add `-m security` after `pytest` to run only the tests that guard a [SECURITY.md](SECURITY.md) invariant, or
  `-k <name>` for one test.
- With uv installed instead: from `backend/`, `uv run pytest` with `POSTGRES_DB=brain_test` and the other
  `POSTGRES_*` settings pointing at a running database.
- Tests refuse to run unless the database name ends in `_test`, so they can never touch your real data. They create
  and migrate that database themselves.
- Most database tests run inside a transaction that is rolled back. Connector, admin and sync tests commit (as the
  real handlers do) and empty the tables they touch instead. Audit records can't be removed (the log is
  append-only), so those tests leave theirs behind, each in its own company's chain.
- Tests never call real services: the LLM is faked (`helpers.FakeLLM`), and Google, Slack and Atlassian are faked at
  the HTTP layer.

| File | Covers |
|---|---|
| `test_search.py` | Company isolation, ACL and boundary filtering, keyword and vector search |
| `test_live_check.py` | Deny by default: false, missing, errors, timeouts, unlinked accounts |
| `test_grounding.py` | Citation checking, fallback answer, untrusted text containment |
| `test_query_pipeline.py` | What the LLM sees, when it is skipped, what is audited |
| `test_api.py` | Session-only identity, strict request bodies, development-only routes |
| `test_connections_api.py` | Connector sign-in into the right company, principals, token refresh, disconnect |
| `test_drive.py`, `test_slack.py`, `test_atlassian.py` | Fetch and ACL per source, live checks (`can_read`), retries |
| `test_sync.py` | Chunking, upserts, soft deletes, embedding catch-up, live checks as the user |
| `test_admin.py` | Admin-only boundary and sync API, scoped to the admin's company, audited |
| `test_audit.py` | Per-company hash chains, tampering detected, the app role can't change the log, concurrent writes, admin search and verify |

## 2. Frontend checks

From `frontend/`, with Node.js 24 ([RUNNING.md](RUNNING.md) §1):

| Run | Catches | ✅ |
|---|---|---|
| `npm ci` | Installs exactly the locked dependencies | No errors |
| `npx tsc --noEmit` | Type errors, including calls that don't match the backend's API types | No output |
| `npm test` | Vitest unit tests (below) | All pass (53 on 8 Oct) |
| `npm run build` | Anything that breaks the production build, and pages that wrongly try to render at build time | "Compiled successfully" and a route list |

The unit tests sit next to the code they test (`*.test.ts`) and cover the security-relevant helpers: which fixed
reply an answer is, which source links are safe, removing `[S1]` markers, mock mode staying off in production, and
the allowlist of sign-in error codes (`lib/connectors.test.ts`).

To run the frontend with live reloading while you edit: [frontend/README.md](../frontend/README.md) ("Running").

## 3. Security invariants

[SECURITY.md](SECURITY.md) §2 lists the rules KnowBuddy must never break (for example, "an unauthorized document
never reaches the LLM"). Its **Test status** column links each rule to the tests that would fail if it broke; run
them alone with `-m security` (section 1). When you add or change a rule, add a test for it and link it from that
table ([CONTRIBUTING.md](../CONTRIBUTING.md) §8).

## 4. Manual checks

Things the automated tests can't show: the real LLM, the real tools, and how it looks.

**With the demo personas** ([RUNNING.md](RUNNING.md) §4). Answers come from the real LLM, so check the state and the
sources, not the exact wording:

| As | Ask | Expected |
|---|---|---|
| Alice | What's blocking the payment gateway migration? | An answer citing `#payments-oncall` (Slack) |
| Alice | What does the runbook say about failover? | An answer citing the Drive runbook and/or `#eng` |
| Ben | What's blocking the payment gateway migration? | Less, or "not found" (he isn't in `#payments-oncall`) |
| Charlie | What happened in the Q3 security incident? | The fixed "not found" reply (scenario 3) |
| Priya | What happened in the Q3 security incident? | An answer citing the incident report and/or `#security-incidents` |
| Dana | What's blocking the payment gateway migration? | Only Kopi Labs' own content, never MerlionPay's |
| anyone | What are the salary bands? | "Not found": that folder is outside the admin boundary |
| anyone | asdkjh qwe | "Not found", looking exactly like Charlie's |

Also:
- Stop the backend (`docker compose stop backend`) and ask: "Couldn't reach the server", with **Try again**.
- Sign out in another tab, then ask: you're taken to `/login`.
- As Alice, open `/admin/audit`: you're sent back to the chat. As Priya, both admin pages open.

**With your own tools** ([RUNNING.md](RUNNING.md) §5). Replace `<POSTGRES_USER>` and `<POSTGRES_DB>` with the values in
your `backend/.env`:

- **Same session as the app:** after connecting, open http://localhost:8000/api/me. ✅ It shows your email.
- **Tokens are encrypted at rest:**
  ```bash
  docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "select provider, left(encode(access_token,'escape'),6) from connections;"
  ```
  ✅ The token column shows `gAAAAA` (encrypted), never a real token.
- **Principals are written:**
  ```bash
  docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "select * from user_principals;"
  ```
  ✅ After connecting Drive: `google:user:<your email>` and `google:domain:<your domain>`.
- **Outsiders are refused:** connect Slack with a token from another workspace while you're already in a company.
  ✅ "That sign-in belongs to no company you can join" (or "already linked to someone else"), and your company is
  unchanged.
- **Revocations apply at once:** after a sync, remove a teammate from a private channel in the boundary, then ask
  about it as them. ✅ The answer no longer uses that channel, before any new sync.
- **Disconnect:** click **Disconnect**. ✅ The tool shows **Connect** again, its rows are gone from
  `user_principals`, and (for Google) the app is gone from https://myaccount.google.com/permissions.
- **Sign out:** at http://localhost:8000/docs, run **`DELETE /api/session`**. ✅ **Test** on the Connections page now
  sends you to `/login`.

## 5. Accessibility

Target: WCAG 2.2 AA. On 4 Oct every page and every chat state, light and dark, had no violations.

- **Automated:** install the free **axe DevTools** browser extension (or use Chrome's Lighthouse → Accessibility) and
  run it on `/login`, the chat (empty, and with an answer), `/connectors`, and both admin pages with the design
  preview open. Check light and dark (the theme button in the header). ✅ No violations.
- **Keyboard:** press Tab from the top of a page. ✅ The first stop is "Skip to content", every control shows a
  focus ring, menus open with Enter and close with Escape, and dialogs return focus to what opened them.
- **Phone width:** in the browser's developer tools, set the width to 375 px. ✅ Nothing scrolls sideways, the
  header links move into the account menu, and buttons are at least 44 px tall on touch screens.
- **Not yet checked:** a full pass with a screen reader (VoiceOver or NVDA).

The accessibility rules the frontend follows: [architecture/FRONTEND.md](architecture/FRONTEND.md) ("Accessibility").

## 6. Mock mode

Shows every chat state without spending LLM tokens. Development only.

1. Add `NEXT_PUBLIC_API_MOCK=1` to `frontend/.env`, and run the frontend dev server (section 2's link). Mock mode
   is ignored by production builds, including the Docker image.
2. Sign in as usual: only chat answers are faked, so the backend must still be running.
3. Put a keyword in the question to choose the reply: `mock:answered` (default), `mock:long`, `mock:markers`,
   `mock:bad-url`, `mock:no-citations`, `mock:not-found`, `mock:unavailable`, `mock:401`, `mock:422`, `mock:503`,
   `mock:offline`. Replies take about 6 seconds; add `mock:fast` to skip the wait.

✅ A **MOCK DATA** badge shows in the header, and mocked answers say "Ref # — (mock)". Fixtures are in
`frontend/lib/api/mock.ts`. Remove the setting when you're done.

## 7. Before a pull request, before submitting

**Before a pull request:**
- Backend tests (section 1), if you touched `backend/`.
- All four frontend checks (section 2), if you touched `frontend/`.
- `python3 scripts/check_doc_links.py`, if you touched any `.md` file.
- The manual checks (section 4) for what you changed, and accessibility (section 5) if you changed a page.
- Write what you ran and the results in the PR's "How it was tested" ([CONTRIBUTING.md](../CONTRIBUTING.md) §3).

**Before submitting:** the quality gates in [hackathon/submission.md](hackathon/submission.md), including the
end-to-end run on a clean machine.

## 8. When tests go wrong

| Symptom | Cause and fix |
|---|---|
| "Refusing to run tests against database …: POSTGRES_DB must end with '_test'" | You left out `-e POSTGRES_DB=brain_test`. Copy the command in section 1 exactly |
| The backend test command can't connect to the database | Start it first: `docker compose up -d db` |
| `npx: command not found` or the wrong Node version | Node 24 isn't on your PATH (Homebrew: [RUNNING.md](RUNNING.md) §1) |
| `tsc` complains about files in `.next/types` or `.next/dev/types` | Leftovers from an older build: delete those two folders, then run it again |
| Port 3000 is already in use when starting the dev server | The Docker frontend holds it: `npm run dev -- -p 3001` |
| A test passes alone but fails with the others | A committing test left rows behind: check it empties the tables it touches (section 1) |

## 9. Not covered yet

- No component tests for the chat page: its states are checked by hand (sections 4 and 6).
- Signing in with real Google, Slack and Atlassian accounts is only checked by hand (section 4), never automatically.
- Live permission checks are unit-tested with fakes, not run automatically against real workspaces.
- No end-to-end browser test of the whole flow.

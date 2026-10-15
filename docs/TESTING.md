# Testing KnowBuddy

**For:** anyone checking that a change works, before a pull request or before submitting.
**You'll:** run the automated tests, then check by hand what they can't cover.
**Not here:** running the app → [RUNNING.md](RUNNING.md) · how to write tests (naming, fake data, security tests) →
[CONTRIBUTING.md](../CONTRIBUTING.md) §8.

**Contents:** 1. Backend tests · 2. Frontend checks · 3. Security invariants · 4. Manual checks · 5. Accessibility ·
6. Mock mode · 7. Before a pull request, before submitting · 8. When tests go wrong · 9. Search at scale ·
10. Not covered yet

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
| `test_injection.py` | Prompt injection: the source fence in every spelling, the scanner (attacks found in English and Chinese, ordinary lines left alone), answer suppression, invented links, the audit record and the API |
| `test_query_pipeline.py` | What the LLM sees, when it is skipped, what is audited |
| `test_redaction.py` | Need-to-Know Shield: each detector, need-to-know, secrets always, answer guard, hostile input |
| `test_api.py` | Session-only identity, strict request bodies, development-only routes |
| `test_connections_api.py` | Connector sign-in into the right company, principals, token refresh, disconnect |
| `test_drive.py`, `test_slack.py`, `test_atlassian.py` | Fetch and ACL per source, live checks (`can_read`), retries |
| `test_sync.py` | Chunking, upserts, soft deletes, embedding catch-up, live checks as the user |
| `test_admin.py` | Admin-only boundary and sync API, scoped to the admin's company, audited |
| `test_audit.py` | Per-company hash chains, tampering detected, the app role can't change the log, concurrent writes, admin search and verify |
| `test_audit_assistant.py` | Audit assistant (ADR-013): the model's plan can only narrow a search of the admin's own company, bad values are dropped, names resolve inside that company or turn into a clarifying question; counts come from code; a record shown to the model holds no hashes, principals or ACLs; a logged question can't plant an instruction or fake our tags; invented citations and links are removed; `POST /api/admin/audit/ask` is admins only, answers the challenge's audit inquiry, and records one `audit_asked` event even when the LLM fails |
| `test_seed.py` | The demo seed's permission cases (who finds which story document: the private `#db-team` thread, the contract terms, the breach report, the other company's ticket) and the Company A filler (its size, the same every run, added once, removed cleanly) |

## 2. Frontend checks

From `frontend/`, with Node.js 24 ([RUNNING.md](RUNNING.md) §1):

| Run | Catches | ✅ |
|---|---|---|
| `npm ci` | Installs exactly the locked dependencies | No errors |
| `npx tsc --noEmit` | Type errors, including calls that don't match the backend's API types | No output |
| `npm test` | Vitest unit tests (below) | All pass (152 on 9 Oct) |
| `npm run build` | Anything that breaks the production build, and pages that wrongly try to render at build time | "Compiled successfully" and a route list |

The unit tests sit next to the code they test (`*.test.ts`) and cover the security-relevant helpers: which fixed
reply an answer is, which source links are safe, turning `[S1]` markers into the right numbered source by label (and removing them for Copy), mock mode staying off in production, and
the allowlist of sign-in error codes (`lib/connectors.test.ts`), how fresh a source is
(`lib/citations.test.ts`: "synced" only for data that ever synced, stale after 15 minutes), which masked values a reader
can see (`lib/masking.test.ts`: the Shield's tags, never `[S1]`), the
`mock:shield` and `mock:injection` fixtures, and the audit page's filters and one-line summaries
(`lib/audit.test.ts`: dates become a whole-day range, a scope ID is only sent with its tool, malformed values in the
URL are dropped, the open record is read from and written to the URL, every event type gets a readable line, and
the record dialog's Documents table merges every list into one row per document, in label order),
and the boundary page's rules (`lib/boundary.test.ts`: a tool's own 401 or 502 is never mistaken for being signed out
or the server being down, an unrecognised error fails safe, each scope's status, which scopes can't sync, and
when a "sync now" has finished).

To run the frontend with live reloading while you edit: [frontend/README.md](../frontend/README.md) ("Commands").

## 3. Security invariants

[SECURITY.md](SECURITY.md) §2 lists the rules KnowBuddy must never break (for example, "an unauthorized document
never reaches the LLM"). Its **Test status** column links each rule to the tests that would fail if it broke; run
them alone with `-m security` (section 1). When you add or change a rule, add a test for it and link it from that
table ([CONTRIBUTING.md](../CONTRIBUTING.md) §8).

## 4. Manual checks

Things the automated tests can't show: the real LLM, the real tools, and how it looks.

**Search at Company A's size** (11 Oct, laptop, Docker): after `python -m app.seed --scale --embed` (21,009
MerlionPay documents, 2,567 chunks with embeddings), permission-filtered search per question, median of 15:

| Person | Keyword only | Keyword + meaning |
|---|---|---|
| Alice (wide access) | 21 ms | 109 ms (162 ms at most) |
| Charlie (narrow access) | 3 ms | 4 ms |

The demo questions still return their story documents first. The LLM call (about 2 s) dominates a question's time.

**With the demo personas** ([RUNNING.md](RUNNING.md) §4). Answers come from the real LLM, so check the state and the
sources, not the exact wording:

| As | Ask | Expected |
|---|---|---|
| Alice | What's blocking the payment gateway migration? | An answer citing `#payments-oncall` (Slack) |
| Alice | What does the runbook say about failover? | An answer citing the Drive runbook and/or `#eng` |
| Ben | What's blocking the payment gateway migration? | Less, or "not found" (he isn't in `#payments-oncall`) |
| Charlie | What happened in the Q3 security incident? | The fixed "not found" reply (scenario 3) |
| Priya | What happened in the Q3 security incident? | An answer citing the incident report and/or `#security-incidents` |
| Dana | How did the payment gateway migration go? | Kopi Labs' own answer ("finished last week with no blockers"), never MerlionPay's |
| anyone | What are the salary bands? | "Not found": that folder is outside the admin boundary |
| anyone | asdkjh qwe | "Not found", looking exactly like Charlie's |
| Alice | What is the status of the payment gateway migration? | The certificate blocker, never "cancelled" or a "re-verify" link: the planted ops-bot line in `#eng` is removed (ADR-011) |

Also:
- Stop the backend (`docker compose stop backend`) and ask: "Couldn't reach the server", with **Try again**.
- Sign out in another tab, then ask: you're taken to `/login`.
- As Alice, open `/admin/audit`: you're sent back to the chat. As Priya, both admin pages open.

**The live prompt-injection check** sends 10 attacks to the real model, each with and without our checks
(60 short TokenHub calls with `--runs 3`; needs the `LLM_*` settings in `backend/.env`):

```bash
docker compose run --rm --build --no-deps backend python -m app.llm.injection_eval --runs 3
```

✅ Every row says "resisted" in the **KnowBuddy** column. Last run (8 Oct, `hy3`): 30 of 30 in both columns; what
acted is recorded in ADR-011.

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
  run it on `/login`, the chat (empty, and with an answer), `/connectors`, and both admin pages (an audit
  record open, and the boundary's removal dialog open). Check light and dark (Theme in the account menu at the bottom of the sidebar; the top-bar button on the sign-in page). ✅ No violations.
- **Keyboard:** press Tab from the top of a page. ✅ The first stop is "Skip to content", every control shows a
  focus ring, menus open with Enter and close with Escape, and dialogs return focus to what opened them.
- **Phone width:** in the browser's developer tools, set the width to 375 px. ✅ Nothing scrolls sideways, the
  sidebar becomes a top bar whose menu button opens it in a sheet, and buttons are at least 44 px tall on touch screens.
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

✅ A **MOCK DATA** badge shows at the top of the sidebar (in the top bar on phones), and mocked answers say "Ref # — (mock)". Fixtures are in
`frontend/lib/api/mock.ts`. Remove the setting when you're done.

## 7. Before a pull request, before submitting

**Before a pull request:**
- Backend tests (section 1), if you touched `backend/`.
- All four frontend checks (section 2), if you touched `frontend/`.
- `python3 scripts/check_doc_links.py`, if you touched any `.md` file.
- The manual checks (section 4) for what you changed, and accessibility (section 5) if you changed a page.
- Write what you ran and the results in the PR's "How it was tested" ([CONTRIBUTING.md](../CONTRIBUTING.md) §3).

**CI runs the automated ones again on every pull request**
([.github/workflows/ci.yml](../.github/workflows/ci.yml)): the backend tests, the four frontend checks and the doc
link check, shown as three checks on the pull request. They are required for main
([DEPLOYMENT.md](DEPLOYMENT.md) §8), so a pull request can't merge until all three pass. Running them locally first is
still faster than waiting for CI to fail.

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

## 9. Search at scale

How fast search is at about Company A's size (issue #31). `backend/scripts/load_search.py` drops and recreates a
database whose name must end in `_loadtest`, seeds synthetic chunks (random 1,024-d unit vectors, Zipf-distributed
words, ACLs shaped like the connectors': team user lists, workspace-wide, a security team, 1% public), and times
`hybrid_search` and the audit-only `restricted_matches` for three personas, 8 questions × 5 runs each:

```bash
docker compose run --rm --build -e POSTGRES_DB=brain_loadtest -v ./backend/scripts:/app/scripts     backend python -m scripts.load_search --chunks 100000
```

Add `--measure-only` to time an already seeded database again, and `-e PLANS=1` to print each persona's
EXPLAIN ANALYZE. Seeding 100k chunks takes about 12 minutes.

Measured 11 Oct 2026 on a laptop (Docker Desktop on Windows, 7.4 GB for the VM), the `pgvector/pgvector:pg17`
image with its default settings, warm cache:

| Chunks | Persona (sees) | Search p50 | Search p95 | Audit-only search p50 | p95 |
|---|---|---|---|---|---|
| 10k | employee (42%) | 218 ms | 481 ms | 50 ms | 167 ms |
| 10k | security (51%) | 151 ms | 377 ms | 24 ms | 146 ms |
| 10k | contractor (1.3%) | 7 ms | 16 ms | 12 ms | 95 ms |
| 100k | employee (42%) | 427 ms | 901 ms | 123 ms | 757 ms |
| 100k | security (51%) | 462 ms | 1,147 ms | 103 ms | 722 ms |
| 100k | contractor (1.5%) | 33 ms | 126 ms | 102 ms | 748 ms |

What the plans show (the four questions in #31):

1. **Vector search** uses the HNSW index at 100k chunks for the broad personas, even though `pool` is materialised.
   At 10k, and for the contractor at 100k, Postgres computes exact distances over the permitted chunks instead,
   which is cheaper there.
2. **Narrow ACLs still fill the result**: every persona, the contractor included, gets the full 50 vector rows
   (iterative scan does not stop early at this size).
3. **Keyword search is the main cost.** Common question words ("status", "payment") match about 45% of chunks, so
   the query reads the whole `chunks` table and ranks 16,000–19,000 permitted matches with `ts_rank_cd` before its
   LIMIT.
4. **The audit-only search** adds 100–140 ms at p50 to every question, and up to 0.75 s at p95, for the same reason.

The boundary check costs a few milliseconds (a hash join against `boundary`), so a `documents.in_boundary` column is
not needed. At 100k chunks the working set is about 2.5 GB (`chunks` 1.7 GB, its HNSW index 0.8 GB) against
Postgres's default 128 MB `shared_buffers`, so a cold cache was much slower (one 5.6 s p95 on the first pass).
Follow-ups: cheaper keyword ranking for common words, and sizing `shared_buffers` and memory for the production
database before it holds this much.

Measured again 12 Oct 2026 after BM25 replaced `ts_rank_cd` (ADR-012, `paradedb/paradedb:v0.26.1-pg17`, same laptop,
100k chunks): employee 280 ms p50 / 373 ms p95, security 356 / 444 ms, contractor 75 / 162 ms; the audit-only search
71 / 139, 72 / 125 and 52 / 102 ms. BM25 ranks only its best matches instead of every permitted match, so the
keyword cost above is gone; the contractor, who sees little, is a little slower but still the fastest.

## 10. Retrieval quality

Does the right source reach the model, is it the latest version, and does an answerable question get an answer
(ADR-012)? `backend/scripts/eval_retrieval.py` drops and recreates a database whose name must end in `_eval`,
writes a fictional company's long documents ([eval_corpus.py](../backend/scripts/eval_corpus.py): runbooks,
policies, Jira tickets, Slack threads, some later updated) through the real sync path, next to the ~21,000 filler
documents as distractors (1,000 of them embedded), and asks 41 questions as a full-access persona: 25 specific,
6 broad ("What is the team working on right now?"), 5 about something that changed, 5 off-topic. A restricted
persona asks them too, to count leaks. It calls TokenHub (about 1,100 embeddings; with `--answers` also 41
answers), and takes 3–5 minutes.

```bash
docker compose run --rm --build -e POSTGRES_DB=brain_eval -v ./backend/scripts:/app/scripts backend python -m scripts.eval_retrieval --answers
```

(Git Bash on Windows: prefix `MSYS_NO_PATHCONV=1`, or the mount path is rewritten.) It exits 1 on any leak or
superseded text left in the index. Change one thing at a time and compare with the last recorded run.

Measured 12 Oct 2026, `hy3`. "Reaches the LLM": a snippet that answers the question is in the text sent for a
correct source. Before: `main` at 968eb23. After: ADR-012.

| | Before | After |
|---|---|---|
| Specific: correct source in top 5 / reaches the LLM / answered | 25/25 / 25/25 / 25/25 | 25/25 / 25/25 / 25/25 |
| Broad: correct source in top 5 / reaches the LLM / answered | 5/6 / 5/6 / 5/6 | 4/6 / 6/6 / 6/6 |
| Changed: reaches the LLM / answered / answer has the new value | 3/5 / 3/5 / 3/5 | 5/5 / 5/5 / 5/5 |
| Off-topic: answered "not found" | 5/5 | 5/5 |
| Leaks / superseded text in the index | 0 / 0 | 0 / 0 |

Prompt changes also need the injection evaluation (section 4) to stay at 30/30: the first wording of the
partial-answer rule dropped it to 27/30 and was rejected (ADR-012).

## 11. Not covered yet

- No component tests for the chat page: its states are checked by hand (sections 4 and 6).
- Signing in with real Google, Slack and Atlassian accounts is only checked by hand (section 4), never automatically.
- Live permission checks are unit-tested with fakes, not run automatically against real workspaces.
- No end-to-end browser test of the whole flow.

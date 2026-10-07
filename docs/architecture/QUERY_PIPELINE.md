# Query pipeline and shared contracts

What roadmap Task 3 built, and the formats Tasks 1 and 2 build against.
Decisions behind it: ADR-002, ADR-003, ADR-005, ADR-006, ADR-007 in
[DECISIONS.md](../decisions/DECISIONS.md).

## 1. For connectors (Task 1): what to write

Schema: [0002_core_schema.py](../../backend/migrations/versions/0002_core_schema.py),
plus an HNSW vector index in [0003_chunks_embedding_hnsw.py](../../backend/migrations/versions/0003_chunks_embedding_hnsw.py).

| Table | Written by | Notes |
|---|---|---|
| `companies` | First full member to connect Slack from a new workspace; its admin adds the Atlassian site (`app/companies.py`) | Every document, boundary scope and cursor belongs to one (migration 0005). A user has one once a Slack or Atlassian connection names it; until then they see nothing |
| `documents` | Connector | One row per item (Slack thread, Drive file). Unique on `(company_id, source, source_id)` |
| `chunks` | Connector worker | Pieces of a document's text, at most **2,000 characters** each (TokenHub embedding limit) |
| `sync_state` | Connector | Cursors, one row per `(company_id, source, key)` (not used yet: sync rescans each scope) |
| `boundary` | Admin action (`/api/admin/boundary`) | Which channels, folders, projects and spaces each company may use at all |
| `users`, `user_principals` | Sign-in | Who a person is on each platform |

Rules for connectors:

- **`documents.acl`** holds the item's principals in the formats from
  [docs/connectors/](../connectors/), e.g. `slack:user:U024`, `slack:members`,
  `google:user:a@co.com`, `google:domain:co.com`, `public`. Stored once per
  document; chunks inherit it. It may include extra people but must never leave
  out a real reader.
- **`documents.company_id`** is the company that synced it. Search only ever
  reads the user's own company, so `public` and `slack:members` never cross
  companies.
- **`documents.scope_id`** is the Slack channel ID, Drive folder ID, Jira project
  key or Confluence space ID that appears in `boundary`. Documents whose
  `(company_id, source, scope_id)` is not in `boundary` are never used.
- **Replace a document's chunks in one transaction** when it changes, and set
  `deleted_at` instead of deleting documents.
- **Embed chunks with `LLMClient.embed()`** from
  [app/llm/client.py](../../backend/app/llm/client.py), so chunks and questions
  use the same model (`kinfra-text-embedding-0.6b`, 1,024 dimensions).
- **Live check:** each connector provides `can_read(principal, ids) -> {id: bool}`,
  where `principal` is the user's own identity on that platform and `ids` are
  `source_id` values: [app/connectors/live.py](../../backend/app/connectors/live.py),
  passed to [app/auth/live_check.py](../../backend/app/auth/live_check.py) by
  `/api/query`. Anything other than `True`, including an exception or taking
  longer than 2 seconds, denies.

## 2. For the frontend (Task 2): the API

All routes are under `/api`. Identity comes only from the `ib_session` cookie.

| Method and path | Body | Returns |
|---|---|---|
| `POST /api/query` | `{"question": "..."}` (1 to 2,000 characters, no other fields) | `{"answer", "citations": [{"id", "title", "url", "source", "updated_at", "synced_at"}], "audit_id"}`. `updated_at`: last edit at the source. `synced_at`: when our copy was last confirmed against the source (null = never, e.g. seeded); show it as "as of" so stale content never looks current |
| `GET /api/me` | | `{"email", "name", "is_admin"}`, or 401 if not signed in |
| `DELETE /api/session` | | 204, signs out |
| `GET /api/dev/users` | | Seeded users. **Development only** |
| `POST /api/dev/session` | `{"user_id": 1}` | Signs in as that user (persona switcher). **Development only** |

- **Sign-in:** there is no username/password page (ADR-002). The product signs
  in through "Connect Slack" / "Connect Google" (`/connectors`, see
  [GUIDE.md](../connectors/GUIDE.md)), which sets the same session cookie. The
  persona switcher uses the development routes, which do not exist unless
  `APP_ENV=development`.
- **Cookies:** call the API with credentials included. The session cookie is
  httpOnly and SameSite=Lax; keeping the API on the same origin as the frontend
  (for example a Next.js rewrite of `/api`) avoids cross-origin cookie issues.
- **Fixed replies** the UI should recognise: "I could not find this in the
  sources you have access to." and "The assistant is unavailable right now.
  Please try again shortly."

## 3. What happens on `POST /api/query`

[app/pipeline/query.py](../../backend/app/pipeline/query.py):

1. Session cookie to user to principals (`public` is added for everyone).
2. Embed the question. If that fails, continue with keyword search only.
3. One SQL query ([app/retrieval/search.py](../../backend/app/retrieval/search.py)):
   only the user's own company's documents that are not deleted, whose ACL
   shares a principal with the user, and whose scope is in the boundary. Keyword and vector ranks are merged
   with reciprocal rank fusion; top 20 documents, up to 3 chunks each. Vector
   search can use the HNSW index and runs with `hnsw.iterative_scan` on, so the
   permission filter cannot starve it. The index is approximate: it can
   occasionally miss a document, which makes an answer less complete but never
   leaks, because only permitted documents are ever returned.
4. Live check per source, in parallel, 2-second timeout. Deny by default.
5. Nothing left: return the fixed "not found" reply without calling the LLM.
6. Up to 10 documents go to the LLM as `<source id="S1">` blocks marked as
   untrusted data, best-ranked chunks first, within 12,000 characters in total
   (prompt size drives response time); replies are capped at 1,024 tokens. The
   model sees short labels, never raw IDs.
7. Citations outside the labels sent are removed; with no valid citation the
   reply becomes the fixed "not found" answer.
8. One `audit_events` row: user, question, search mode, every candidate with
   its decision and reason, what was sent to the LLM, answer, citations, model.
   It also records **restricted matches**: documents the question matched by
   keyword but the user may not see, with the reason. These come from a
   separate audit-only search and never reach the user or the LLM (ADR-007).

The database is used in two short transactions (step 3 with the restricted-match
search, then step 8), so no connection is held while TokenHub or a source is
called. The answer is returned only after its audit row is committed.

## 4. Not built yet, and stubs

| Item | Status | Roadmap |
|---|---|---|
| Live check | Built: `/api/query` asks each source as the user (`app/connectors/live.py`). In development only, a persona with no connection at all (the seed) still uses the stored-ACL stub. The audit log records `live_check_mode` | Task 1 |
| Connector sign-in | Built: creates the user in their company, the session and `user_principals` ([GUIDE.md](../connectors/GUIDE.md)) | Task 1 |
| Sync | Built: `app/sync.py`, every 5 minutes and on `POST /api/admin/sync` | Task 1 |
| Audit hash chain and insert-only DB role | Not built; the table already rejects UPDATE, DELETE and TRUNCATE | Task 3, 5–6 Oct |
| Audit search API | Not built | Task 3, 5–6 Oct |
| Semantic search | Code works; needs the embedding model enabled on the TokenHub key and chunk embeddings written | |

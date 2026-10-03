# Query pipeline and shared contracts

What roadmap Task 3 built, and the formats Tasks 1 and 2 build against.
Decisions behind it: ADR-002, ADR-003, ADR-005, ADR-006, ADR-007 in
[DECISIONS.md](../decisions/DECISIONS.md).

## 1. For connectors (Task 1): what to write

Schema: [0002_core_schema.py](../../backend/migrations/versions/0002_core_schema.py).

| Table | Written by | Notes |
|---|---|---|
| `documents` | Connector | One row per item (Slack thread, Drive file). Unique on `(source, source_id)` |
| `chunks` | Connector worker | Pieces of a document's text, at most **2,000 characters** each (TokenHub embedding limit) |
| `sync_state` | Connector | Cursors, one row per `(source, key)` |
| `boundary` | Admin action | Which channels and folders may be used at all |
| `users`, `user_principals` | Sign-in | Who a person is on each platform |

Rules for connectors:

- **`documents.acl`** holds the item's principals in the formats from
  [docs/connectors/](../connectors/), e.g. `slack:user:U024`, `slack:members`,
  `google:user:a@co.com`, `google:domain:co.com`, `public`. Stored once per
  document; chunks inherit it. It may include extra people but must never leave
  out a real reader.
- **`documents.scope_id`** is the Slack channel ID, or the Drive folder ID that
  appears in `boundary`. Documents whose `(source, scope_id)` is not in
  `boundary` are never used.
- **Replace a document's chunks in one transaction** when it changes, and set
  `deleted_at` instead of deleting documents.
- **Embed chunks with `LLMClient.embed()`** from
  [app/llm/client.py](../../backend/app/llm/client.py), so chunks and questions
  use the same model (`kinfra-text-embedding-0.6b`, 1,024 dimensions).
- **Live check:** each connector provides `can_read(principal, ids) -> {id: bool}`,
  where `principal` is the user's own identity on that platform and `ids` are
  `source_id` values. Register it in `default_checkers` in
  [app/auth/live_check.py](../../backend/app/auth/live_check.py). Anything other
  than `True`, including an exception or taking longer than 2 seconds, denies.

## 2. For the frontend (Task 2): the API

All routes are under `/api`. Identity comes only from the `ib_session` cookie.

| Method and path | Body | Returns |
|---|---|---|
| `POST /api/query` | `{"question": "..."}` (1 to 2,000 characters, no other fields) | `{"answer", "citations": [{"id", "title", "url", "source", "updated_at"}], "audit_id"}` |
| `GET /api/me` | | `{"email", "name", "is_admin"}`, or 401 if not signed in |
| `DELETE /api/session` | | 204, signs out |
| `GET /api/dev/users` | | Seeded users. **Development only** |
| `POST /api/dev/session` | `{"user_id": 1}` | Signs in as that user (persona switcher). **Development only** |

- **Sign-in:** there is no username/password page (ADR-002). The product signs
  in through "Connect Slack" / "Connect Google", which is not built yet. Until
  then the persona switcher uses the development routes, which do not exist
  unless `APP_ENV=development`.
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
   only documents that are not deleted, whose ACL shares a principal with the
   user, and whose scope is in the boundary. Keyword and vector ranks are merged
   with reciprocal rank fusion; top 20 documents, up to 3 chunks each.
4. Live check per source, in parallel, 2-second timeout. Deny by default.
5. Nothing left: return the fixed "not found" reply without calling the LLM.
6. Up to 10 documents go to the LLM as `<source id="S1">` blocks marked as
   untrusted data. The model sees short labels, never raw IDs.
7. Citations outside the labels sent are removed; with no valid citation the
   reply becomes the fixed "not found" answer.
8. One `audit_events` row: user, question, search mode, every candidate with
   its decision and reason, what was sent to the LLM, answer, citations, model.

## 4. Not built yet, and stubs

| Item | Status | Roadmap |
|---|---|---|
| Live check | **STUB:** answers from the stored ACL, so it does not catch revocations between syncs. The audit log records `live_check_mode` | Task 1 provides real `can_read` |
| Connector sign-in | Not built; development routes stand in | |
| Audit hash chain and insert-only DB role | Not built; the table already rejects UPDATE, DELETE and TRUNCATE | Task 3, 5–6 Oct |
| Audit search API | Not built | Task 3, 5–6 Oct |
| Semantic search | Code works; needs the embedding model enabled on the TokenHub key and chunk embeddings written | |

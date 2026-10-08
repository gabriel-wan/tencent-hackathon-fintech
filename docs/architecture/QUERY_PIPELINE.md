# Query pipeline and shared contracts

**For:** anyone changing the question pipeline, or building against its API or tables.
**You'll:** see the exact steps of one question, the API contracts, and what connectors must write.
**Not here:** the overview and diagrams → [ARCHITECTURE.md](../ARCHITECTURE.md) · connectors in depth →
[CONNECTORS.md](CONNECTORS.md).

What roadmap Task 3 built, and the formats Tasks 1 and 2 build against.
Decisions behind it: ADR-002, ADR-003, ADR-005, ADR-006, ADR-007 in
[DECISIONS.md](../decisions/DECISIONS.md).

## 1. For connectors (Task 1): what to write

Schema: [0002_core_schema.py](../../backend/migrations/versions/0002_core_schema.py),
an HNSW vector index in [0003](../../backend/migrations/versions/0003_chunks_embedding_hnsw.py),
connections in [0004](../../backend/migrations/versions/0004_connections.py), companies in
[0005](../../backend/migrations/versions/0005_companies.py), the audit hash chain and app role in
[0006](../../backend/migrations/versions/0006_audit_hash_chain.py), and the app's own login in
[0007](../../backend/migrations/versions/0007_app_role_login.py).

| Table | Written by | Notes |
|---|---|---|
| `companies` | First full member to connect Slack from a new workspace; its admin adds the Atlassian site (`app/companies.py`) | Every document, boundary scope and cursor belongs to one (migration 0005). A user has one once a Slack or Atlassian connection names it; until then they see nothing |
| `documents` | Connector | One row per item (Slack thread, Drive file). Unique on `(company_id, source, source_id)` |
| `chunks` | Connector worker | Pieces of a document's text, at most **2,000 characters** each (TokenHub embedding limit) |
| `sync_state` | Sync | Each scope's last complete sync, one row per `(company_id, source, key)`; shown as `synced_at` on citations and `last_synced_at` on the boundary. No change cursors yet: sync rescans each scope |
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
- **`documents.metadata.need_to_know`** lists the identity principals the source
  names as the item's handlers (Jira assignee and reporter, Drive owners and
  editors, Confluence owner and author). They see its identifiers unmasked
  (ADR-010). Leave it empty when the source names nobody (Slack).
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

The app's routes are under `/api`; sign-in and connections are `/connectors/*` and `/oauth/*` ([CONNECTORS.md](CONNECTORS.md) §3). Identity comes only from the `ib_session` cookie.

| Method and path | Body | Returns |
|---|---|---|
| `POST /api/query` | `{"question": "..."}` (1 to 2,000 characters, no other fields) | `{"answer", "citations": [{"id", "title", "url", "source", "updated_at", "synced_at", "redacted"}], "audit_id"}`. `redacted`: identifiers masked in that source for you, by kind, e.g. `{"card": 1, "phone": 2}` (ADR-010). `updated_at`: last edit at the source. `synced_at`: when our copy was last confirmed against the source (null = never, e.g. seeded); show it as "as of" so stale content never looks current |
| `GET /api/me` | | `{"email", "name", "is_admin"}`, or 401 if not signed in |
| `DELETE /api/session` | | 204, signs out |
| `GET /api/dev/users` | | Seeded users. **Development only** |
| `POST /api/dev/session` | `{"user_id": 1}` | Signs in as that user (persona switcher). **Development only** |
| `GET /api/admin/boundary`, `PUT`/`DELETE /api/admin/boundary/{source}/{scope_id}`, `GET /api/admin/scopes/{source}`, `POST /api/admin/sync` | | The company's boundary and sync. **Admins only** ([CONNECTORS.md](CONNECTORS.md) §3) |
| `GET /api/admin/audit` | Query: `user`, `since`, `until`, `event_type`, `document`, `source`, `scope_id`, `before_id`, `limit` | `{"records": [{"id", "ts", "user_email", "event_type", "payload", "prev_hash", "hash"}], "next_before_id"}`, newest first, own company only. **Admins only**; each search is itself audited |
| `POST /api/admin/audit/verify` | | `{"ok", "checked", "first_broken_id", "reason", "head": {"id", "hash"}}`: recomputes the company's hash chain. **Admins only**; audited |

- **Sign-in:** there is no username/password page (ADR-002). People sign in on
  `/login` with Google, Slack or Atlassian, which connects that tool and sets
  the same session cookie ([CONNECTORS.md](CONNECTORS.md)); in development
  Slack is connected with a pasted token on `/login` or `/connectors`. The
  persona switcher uses the development routes, which do not exist unless
  `APP_ENV=development`.
- **Cookies:** call the API with credentials included. The session cookie is
  httpOnly and SameSite=Lax. The frontend keeps the API on its own origin with
  a proxy route (`frontend/app/api/[...path]/route.ts`), so there are no
  cross-origin cookie issues.
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
   Otherwise the **Need-to-Know Shield** ([app/redaction.py](../../backend/app/redaction.py), ADR-010)
   masks each source's title, link and text: cards, NRIC/FIN, accounts, IBANs, passports,
   dates of birth, phones, non-colleague emails, non-colleague names (labelled, or a mention of a name labelled in any
   source of the question) and Singapore
   addresses, unless the user holds one of the document's
   `metadata.need_to_know` identities; secrets always. Secrets in the question are masked
   before step 2.
6. Up to 10 documents go to the LLM as `<source id="S1">` blocks marked as
   untrusted data, best-ranked chunks first, within 12,000 characters in total
   (smaller prompts answer faster); replies are capped at 1,024 tokens, with
   `hy3`'s hidden reasoning turned off (ADR-006). The model sees short labels,
   never raw IDs.
7. Citations outside the labels sent are removed; with no valid citation the
   reply becomes the fixed "not found" answer. The answer guard then masks any
   identifier the model was not shown unmasked and the user did not type.
8. One `audit_events` row: user, question, search mode, every candidate with
   its decision and reason, what was sent to the LLM, answer, citations, model,
   and `timings_ms` per step (embed, search, live_check, llm, total; also logged).
   `redactions` and `answer_masked` hold, per source, need-to-know and the count
   masked per kind: counts, never values. The question and answer are stored
   fully masked, even when the user saw them unmasked, including where a value
   reappears without its label (ADR-010).
   It also records **restricted matches**: documents the question matched by
   keyword but the user may not see, with the reason. These come from a
   separate audit-only search and never reach the user or the LLM (ADR-007).

The database is used in two short transactions (step 3 with the restricted-match
search, then step 8), so no connection is held while TokenHub or a source is
called. The answer is returned only after its audit row is committed.

## 4. Status

| Item | Status | Roadmap |
|---|---|---|
| Live check | Built: `/api/query` asks each source as the user (`app/connectors/live.py`). In development only, a persona with no connection at all (the seed) still uses the stored-ACL stub. The audit log records `live_check_mode` | Task 1 |
| Connector sign-in | Built: creates the user in their company, the session and `user_principals` ([CONNECTORS.md](CONNECTORS.md)) | Task 1 |
| Sync | Built: `app/sync.py`, every 5 minutes and on `POST /api/admin/sync` | Task 1 |
| Audit hash chain and insert-only DB role | Built: one chain per company (`app/audit/log.py`, migrations 0006 and 0007); the app logs in as `knowbuddy_app`, which can read and add audit records only | Task 3 |
| Audit search API | Built: `GET /api/admin/audit` and `POST /api/admin/audit/verify` (`app/audit/api.py`), admins only, own company only, each use audited | Task 3 |
| Semantic search | Built: sync embeds every chunk through TokenHub; keyword search still works if embedding fails | |

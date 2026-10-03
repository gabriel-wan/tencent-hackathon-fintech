# backend/

FastAPI service (ADR-001). Contracts and the query flow are described in
[docs/architecture/QUERY_PIPELINE.md](../docs/architecture/QUERY_PIPELINE.md).

| Module | Responsibility |
|---|---|
| `app/api/` | HTTP routes and dependencies. Development-only routes exist only when `APP_ENV=development` |
| `app/auth/` | Sessions, principals and the live permission check. The security boundary lives here and in the search SQL |
| `app/retrieval/search.py` | Hybrid search, filtered by ACL and admin boundary before ranking |
| `app/llm/` | TokenHub client (chat and the shared `embed()`), grounding rules |
| `app/pipeline/query.py` | Question to answer, end to end, with one audit event |
| `app/audit/log.py` | Audit event writes (hash chain not built yet) |
| `app/seed.py` | Fictional development data. Not connector data |
| `migrations/` | Alembic schema migrations |

Keep authorization in `app/auth/` and the search filter: retrieval and LLM
code depend on it, never the other way round. See
[SECURITY.md](../docs/SECURITY.md) for the invariants and which tests cover them.

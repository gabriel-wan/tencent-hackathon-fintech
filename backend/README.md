# backend/

FastAPI service (ADR-001). Contracts and the query flow are described in
[docs/architecture/QUERY_PIPELINE.md](../docs/architecture/QUERY_PIPELINE.md).

| Module | Responsibility |
|---|---|
| `app/api/` | HTTP routes and dependencies. Development-only routes exist only when `APP_ENV=development` |
| `app/auth/` | Sessions, principals and the live permission check. The security boundary lives here and in the search SQL |
| `app/connectors/` | Connector sign-in (OAuth), stored connections, per-source API clients and live checks, and the admin boundary API (`admin.py`) |
| `app/companies.py` | Which company a sign-in belongs to; only a full Slack member can start one |
| `app/sync.py` | Copies each company's boundary scopes into `documents` and `chunks` every 5 minutes, as its admin |
| `app/retrieval/search.py` | Hybrid search, filtered by ACL and admin boundary before ranking |
| `app/llm/` | TokenHub client (chat and the shared `embed()`), grounding rules |
| `app/pipeline/query.py` | Question to answer, end to end, with one audit event |
| `app/audit/` | Tamper-evident audit log: per-company hash chain, verify and search (`log.py`), admin API (`api.py`) |
| `app/db.py` | Database engines: the app logs in as `knowbuddy_app` (`APP_DB_PASSWORD`); `owner_engine()` is for migrations and tests only |
| `app/seed.py` | Fictional development data. Not connector data |
| `migrations/` | Alembic schema migrations |

Keep authorization in `app/auth/` and the search filter: retrieval and LLM
code depend on it, never the other way round. See
[SECURITY.md](../docs/SECURITY.md) for the invariants and which tests cover them.

## Connectors

`app/connectors/` holds one module per source, plus sign-in (`oauth.py`), stored
connections (`store.py`) and the HTTP routes (`api.py`). Connecting a tool signs
the user in (`app/auth/session.py`) and writes their principals to `user_principals`.
Connectors depend on `app/auth/`, never the other way round.

Setting up each tool: [docs/connectors/SETUP.md](../docs/connectors/SETUP.md). The HTTP and Python APIs and the
document schema: [docs/architecture/CONNECTORS.md](../docs/architecture/CONNECTORS.md). Each tool's API:
[docs/connectors/reference/](../docs/connectors/reference/).

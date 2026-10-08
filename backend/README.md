# Backend

**For:** anyone editing the API, the sync worker or the database.
**You'll:** find what each module does, the commands, and the one dependency rule.
**Not here:** how a question flows through the system → [docs/architecture/QUERY_PIPELINE.md](../docs/architecture/QUERY_PIPELINE.md) ·
connectors in depth → [docs/architecture/CONNECTORS.md](../docs/architecture/CONNECTORS.md) · running the whole app →
[docs/RUNNING.md](../docs/RUNNING.md).

FastAPI, Python 3.12, dependencies managed with uv (ADR-001). The `backend` and `sync` containers both run this code.

## Modules

| Module | Responsibility |
|---|---|
| `app/api/` | HTTP routes and dependencies. Development-only routes exist only when `APP_ENV=development` |
| `app/auth/` | Sessions, principals and the live permission check. The security boundary lives here and in the search SQL |
| `app/connectors/` | Sign-in with each tool (OAuth), stored connections, one API client module per tool, live checks, and the admin boundary API (`admin.py`) |
| `app/companies.py` | Which company a sign-in belongs to; only a full Slack member can start one |
| `app/sync.py` | Copies each company's boundary scopes into `documents` and `chunks` every 5 minutes, as its admin |
| `app/retrieval/search.py` | Hybrid search, filtered by company, ACL and admin boundary before ranking |
| `app/llm/` | TokenHub client (chat and the shared `embed()`), grounding rules, the prompt-injection scanner and its live check (`injection_eval.py`) |
| `app/pipeline/query.py` | Question to answer, end to end, with one audit event |
| `app/audit/` | Tamper-evident audit log: per-company hash chain, verify and search (`log.py`), admin API (`api.py`) |
| `app/db.py` | Database engines: the app logs in as `knowbuddy_app` (`APP_DB_PASSWORD`); `owner_engine()` is for migrations and tests only |
| `app/seed.py` | Fictional development data (the demo personas). Not connector data |
| `migrations/` | Alembic schema migrations, applied by the `migrate` service |
| `tests/` | pytest; what each file covers: [docs/TESTING.md](../docs/TESTING.md) §1 |

**The dependency rule:** authorization lives in `app/auth/` and the search filter. Retrieval, the LLM and the
connectors depend on it, never the other way round. The invariants it upholds, and the tests that guard them:
[docs/SECURITY.md](../docs/SECURITY.md).

## Commands

Run from the repository root; everything runs in Docker.

| Command | Does |
|---|---|
| `docker compose run --rm backend python -m app.seed` | Loads the demo personas and their data (development only). Add `--embed` to compute embeddings too |
| `docker compose run --rm backend python -m app.sync` | Runs one sync now. Options: `--company <id>`, one or more of `slack drive jira confluence` |
| `docker compose logs backend sync` | What the API and the sync worker are doing |
| Backend tests | The Docker command in [docs/TESTING.md](../docs/TESTING.md) §1 |

Every API route, with "Try it out": http://localhost:8000/docs. Adding a dependency, writing a migration, adding a
connector: [CONTRIBUTING.md](../CONTRIBUTING.md) §8.

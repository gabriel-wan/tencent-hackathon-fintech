# backend/

FastAPI service (see DECISIONS.md, ADR-001): `/health` (checks Postgres and
pgvector), sessions (`app/auth.py`) and connectors (`app/connectors/`).

Keep the security boundary visible in the layout: permission-aware filtering
should be a clearly separated module that the retrieval and LLM layers depend
on, not something spread across connectors. See SECURITY.md for the invariants
it must uphold.

## Connectors

`app/connectors/` holds one module per source, plus sign-in (`oauth.py`), stored
connections (`store.py`) and the HTTP routes (`api.py`). Users and sessions are in
`app/auth.py`; connectors depend on it, never the other way round.

Setup (local and production), the HTTP and Python APIs, and the document schema:
[docs/connectors/GUIDE.md](../docs/connectors/GUIDE.md). Per-source API details: `docs/connectors/`.

Tests: `uv run pytest`.

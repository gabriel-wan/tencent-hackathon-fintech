# backend/

FastAPI service (see DECISIONS.md, ADR-001). Currently a skeleton: one `/health`
route that checks Postgres and the pgvector extension.

As code lands here, keep the security boundary visible in the layout:
authorization and permission-aware filtering should be a clearly separated
module (`app/auth/`) that the retrieval and LLM layers depend on, not something
spread across connectors. See SECURITY.md for the invariants that module must
uphold.

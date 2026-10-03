# backend/tests/

Backend tests (pytest) live here, mirroring `backend/app/`. Run from `backend/`: `uv run pytest`.
No test calls a real external API: providers are faked at the HTTP layer.

Priority order for tests (see DEVELOPMENT.md):

1. **Security invariants** (SECURITY.md) - negative permission cases, permission
   revocation, "no unauthorized content reaches the LLM". These are the tests the
   judges' scenarios map onto and they must exist before any demo.
2. **Audit-log integrity** - tamper-evidence checks, completeness of recorded fields.
3. **Connector behaviour** - including mocked connectors, clearly labelled as such.
4. **Query flow** - end-to-end vertical slice.

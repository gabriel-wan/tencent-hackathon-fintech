# backend/tests/

Backend tests (pytest), mirroring `backend/app/`. How to run them:
[docs/DEVELOPMENT.md](../../docs/DEVELOPMENT.md) section 3.

- Tests marked `security` cover a SECURITY.md invariant; run them alone with
  `pytest -m security`. SECURITY.md links each invariant to its tests.
- Database tests run inside one transaction that is rolled back, against a
  database whose name must end in `_test`. Connector API tests commit (as the
  handlers do) and empty the tables they touch instead.
- The LLM is always faked (`helpers.FakeLLM`), so tests never call TokenHub.
  Connector providers are faked at the HTTP layer, so tests never call Google,
  Slack or Atlassian.

| File | Covers |
|---|---|
| `test_search.py` | ACL and boundary filtering, keyword and vector search |
| `test_live_check.py` | Deny by default: false, missing, errors, timeouts, unlinked accounts |
| `test_grounding.py` | Citation checking, fallback answer, untrusted text containment |
| `test_query_pipeline.py` | What the LLM sees, when it is skipped, what is audited |
| `test_api.py` | Session-only identity, strict request bodies, development-only routes |
| `test_connections_api.py` | Connector sign-in, company-only accounts, principals, token refresh, disconnect |
| `test_drive.py`, `test_slack.py`, `test_atlassian.py` | Admin clients, live checks (`can_read`), retries |
| `test_ping_cli.py` | The `python -m app.connectors` credential check |

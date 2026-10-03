# backend/

FastAPI service (see DECISIONS.md, ADR-001). Currently a skeleton: one `/health`
route that checks Postgres and the pgvector extension.

As code lands here, keep the security boundary visible in the layout:
authorization and permission-aware filtering should be a clearly separated
module (`app/auth/`) that the retrieval and LLM layers depend on, not something
spread across connectors. See SECURITY.md for the invariants that module must
uphold.

## Connectors

`app/connectors/` holds one module per source, plus sign-in (`oauth.py`), stored
connections (`store.py`) and the HTTP routes (`api.py`). Users and sessions are in
`app/auth.py`; connectors depend on it, never the other way round.

### Users connect their own accounts (ADR-002)

Like connectors in WorkBuddy or Claude: a user clicks Connect, signs in to the
tool with their company account, and the backend can then call that tool's API
as them. Signing in to the first connector also signs the user in to the app
(server-side session cookie); accounts are linked by email.

| Route | What it does |
|---|---|
| `GET /connectors` | The 4 connectors, each with `connected` and the signed-in account |
| `GET /connectors/{drive,slack,jira,confluence}/connect` | Redirects to the tool's sign-in page |
| `GET /oauth/{google,slack,atlassian}/callback` | The tool redirects back here; then to `FRONTEND_URL/connectors?connected=…` or `?error=…` |
| `GET /connectors/{id}/ping` | Calls the tool's API as you, returns `{"ok": true, "as": "<name>"}` |
| `DELETE /connectors/{id}` | Disconnects (Jira and Confluence share one Atlassian sign-in) |
| `POST /logout` | Ends the session (`app/auth.py`) |

Until the frontend exists, try it in a browser: open
`http://localhost:8000/connectors/drive/connect`, sign in, then open
`http://localhost:8000/connectors/drive/ping`.

One-time setup per tool (an OAuth app, in each tool's developer console). Set
`APP_URL`, `TOKEN_ENCRYPTION_KEY` and the client ID/secret in `backend/.env`, and
register the redirect URI `{APP_URL}/oauth/<provider>/callback`. Missing settings
make `/connect` answer 503 naming the variable, before anyone signs in.

| Tool | Where | Provider | Scopes requested (in `oauth.py`) |
|---|---|---|---|
| Google Drive | console.cloud.google.com → APIs & Services → Credentials → OAuth client (Web) | `google` | `openid email profile drive.readonly` |
| Slack | api.slack.com/apps → OAuth & Permissions → **User** Token Scopes | `slack` | `channels:read channels:history groups:read groups:history users:read users:read.email` |
| Jira + Confluence | developer.atlassian.com/console → OAuth 2.0 (3LO); enable Jira, Confluence and User identity APIs | `atlassian` | `read:jira-work read:jira-user read:confluence-content.all read:confluence-space.summary search:confluence read:me offline_access` |

- Only the company's own Slack workspace (`SLACK_TEAM_ID`) and Atlassian site
  (`ATLASSIAN_CLOUD_ID`) are accepted. Anyone can create a workspace or site and
  put any email on an account there, so without this pin a stranger could sign
  in as a colleague. The Slack team ID is the `T�` part of `app.slack.com/client/T�/` in the
  browser; the Atlassian cloud ID is `cloudId` at `https://<site>.atlassian.net/_edge/tenant_info`.
- Slack only accepts `https://` redirect URIs. Locally, run a tunnel
  (`cloudflared tunnel --url http://localhost:8000`) and set `APP_URL` to the
  `https://` address it prints.
- Google apps in Testing mode issue refresh tokens that expire after 7 days, and
  only listed test users can sign in.
- Tokens are encrypted in Postgres and refreshed automatically. If a tool
  rejects the stored grant, the API answers `401 … connect again`.

Calling a tool's API as a user, from any endpoint (`engine: Db` from `app/db.py`,
`user: User` from `app/auth.py`). Pass the engine, not an open connection:
no database connection should be held while a tool's API is called.

```python
from app.connectors import atlassian, store

store.slack_client(engine, user).conversations_list(types="public_channel,private_channel")
store.drive_service(engine, user).files().list(fields="files(id,name)").execute(num_retries=3)
with store.atlassian_client(engine, user, "jira") as jira:      # or "confluence"
    atlassian.request("POST", "/rest/api/3/search/jql", http=jira, json={...}).json()
```

### Admin credentials and the ping command

The admin's own credentials (`backend/.env`) are for background work such as
sync. Check that they authenticate:

```
docker compose run --rm --no-deps backend python -m app.connectors            # all
docker compose run --rm --no-deps backend python -m app.connectors jira slack # some
```

Each source prints `OK` with the account it acts as, or `FAIL` with the reason
(missing env var, bad token, wrong site, Jira token not admin, Slack scopes
missing). The command exits non-zero if any source fails.

Admin entry points. Every entry point (admin or user) retries rate limits (429)
and transient errors:

| Source | Entry point | Example |
|---|---|---|
| Jira | `atlassian.request` (httpx) | `request("POST", "/rest/api/3/search/jql", json={...}).json()` |
| Confluence | `atlassian.request` (httpx) | `request("GET", "/wiki/api/v2/spaces", params={"limit": 250}).json()` |
| Drive | `drive.service(credentials)` | `service(admin_credentials()).files().list(fields="nextPageToken,files(id,name)").execute(num_retries=3)` |
| Slack | `slack.bot()` or `slack.client(token)` (slack_sdk) | `bot().conversations_list(types="public_channel,private_channel")` |

### Who may see a document

Synced documents carry an `acl` list (formats in §5 of each `docs/connectors/` file).
`store.principals(db, user)` returns the entries a user holds, from their connections
(e.g. `slack:user:U024`, `slack:members`, `google:user:<email>`, `atlassian:user:<id>`).
Search keeps documents whose `acl` overlaps it (`acl && :principals`); the live check
below has the final say, so the set may be too wide but never too narrow.

### Live access checks (ADR-003)

Run on the final context before the LLM. Each returns the IDs the user can read
right now, and leaves out anything that errors (deny by default):

| Source | Call |
|---|---|
| Drive | `drive.can_read(store.google_credentials(engine, user), file_ids)`: one batched request per 100 files |
| Slack | `slack.can_read(slack_user_id, channel_ids)`: checked with the bot |
| Jira, Confluence | Not yet (ADR-004: added later) |

Endpoints and paging rules per source are in `docs/connectors/`.

Tests: `uv run pytest`.

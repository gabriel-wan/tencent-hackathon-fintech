# Connectors guide

Users connect their own Google Drive, Slack, Jira and Confluence accounts. The backend then calls each tool as that user.

- **Part 1 (Setup):** configure the connectors, locally and in production.
- **Part 2 (Development):** the APIs and schemas to build on.

Values in `<angle brackets>` are placeholders. Put real values only in `backend/.env` (ignored by git) or your host's secret store. Never put them in code, docs, chat or screenshots.

# Part 1. Setup

## 1.1 Basics

1. Generate an encryption key (it encrypts stored tokens). From `backend/`:
   ```
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. In `backend/.env` (copied from `.env.example`), set:
   ```
   APP_URL=http://localhost:8000
   TOKEN_ENCRYPTION_KEY=<generated key>
   ```
3. From the repo root, run `docker compose up --build`, then open http://localhost:3000/connectors.
   - ✅ The 4 tools are listed. **Connect** returns 503 naming the variable still missing.

After any `.env` change, restart: Ctrl+C, then `docker compose up`.

## 1.2 Google Drive

At https://console.cloud.google.com:

1. Create or choose a project.
2. **APIs & Services → Library**: enable **Google Drive API**.
3. **Google Auth Platform → Get started**:
   - **App information:** any name; your email as the support email
   - **Audience:** External
   - **Contact information:** your email
   - Agree, then **Create**
4. **Audience → Test users**: add every account that will connect. Leave the status as **Testing**.
5. **Clients → Create client**:
   - Type: **Web application**
   - **Authorized redirect URI:** `{APP_URL}/oauth/google/callback`
6. In `backend/.env`, set:
   ```
   GOOGLE_CLIENT_ID=<client id>
   GOOGLE_CLIENT_SECRET=<client secret>
   GOOGLE_ALLOWED_ACCOUNTS=<your test emails, comma-separated>
   ```
   `GOOGLE_ALLOWED_ACCOUNTS` lists who may connect: a Workspace domain (e.g. `company.com`) admits its Workspace accounts, and an email admits exactly that account. Personal Gmail accounts must be listed one by one.
7. Restart, then click **Connect** on Google Drive. On "Google hasn't verified this app", click **Continue**.
   - ✅ Drive shows your email, and **Test** returns `{"ok":true,"as":"<your email>"}`.

In Testing mode, refresh tokens expire after 7 days: connect again when **Test** says `connect again`.

## 1.3 Slack

Slack accepts only `https` redirect URIs, so locally you need a tunnel.

1. Run `cloudflared tunnel --url http://localhost:8000`. Set `APP_URL=https://<tunnel>`.
2. At https://api.slack.com/apps: **Create New App → From scratch**, in your company workspace.
3. **OAuth & Permissions**:
   - **Redirect URL:** `https://<tunnel>/oauth/slack/callback`
   - **User Token Scopes:** `channels:read`, `channels:history`, `groups:read`, `groups:history`, `users:read`, `users:read.email`
4. In `backend/.env`, set:
   ```
   SLACK_CLIENT_ID=<from Basic Information>
   SLACK_CLIENT_SECRET=<from Basic Information>
   SLACK_TEAM_ID=<the T… part of app.slack.com/client/T…/>
   ```
5. Restart, then open `https://<tunnel>/connectors/slack/connect`.
   - ✅ `https://<tunnel>/connectors/slack/ping` shows your Slack name.

Notes:
- The frontend page can't see a session created on the tunnel address, so check on the backend directly.
- The tunnel address changes every run: update `APP_URL` and the Slack redirect URL each time.

## 1.4 Jira and Confluence

One Atlassian sign-in connects both.

1. At https://developer.atlassian.com/console: **Create → OAuth 2.0 integration**.
2. **Permissions**: add these APIs and scopes:
   - **Jira API:** `read:jira-work`, `read:jira-user`
   - **Confluence API:** `read:confluence-content.all`, `read:confluence-space.summary`, `search:confluence`
   - **User identity API:** `read:me`
3. **Authorization → Callback URL:** `{APP_URL}/oauth/atlassian/callback`
4. In `backend/.env`, set:
   ```
   ATLASSIAN_CLIENT_ID=<from Settings>
   ATLASSIAN_CLIENT_SECRET=<from Settings>
   ATLASSIAN_CLOUD_ID=<cloudId from https://<site>.atlassian.net/_edge/tenant_info>
   ```
5. Restart, then click **Connect** on Jira.
   - ✅ Jira and Confluence both show connected, and **Test** on each shows your name.

`GOOGLE_ALLOWED_ACCOUNTS`, `SLACK_TEAM_ID` and `ATLASSIAN_CLOUD_ID` lock sign-in to the company. Anyone else gets `?error=provider_error`.

## 1.5 Admin credentials (for sync)

Background sync reads as an admin, not as a user.

1. Fill in the admin variables listed in [DEVELOPMENT.md §2](../DEVELOPMENT.md#backend-admin-credentials-background-sync).
2. From the repo root, run:
   ```
   docker compose run --rm --no-deps backend python -m app.connectors
   ```
   - ✅ Each tool prints `OK` and the account it acts as. `FAIL` names the bad setting.

## 1.6 Production

Same steps as above, with these differences:

| Setting | Production |
|---|---|
| `APP_URL` | The public `https://` backend address. https makes cookies `Secure`. |
| Redirect URIs | Registered again in each tool's console, at `{APP_URL}/oauth/<google\|slack\|atlassian>/callback` |
| `FRONTEND_URL` (backend), `BACKEND_LOCAL_URL` (frontend) | The public frontend and backend addresses |
| Slack tunnel | Not needed |
| Google audience | **Internal** if the company uses Google Workspace (no review needed). Otherwise **External**, and publish the app, which requires Google's verification for Drive access. |
| `GOOGLE_ALLOWED_ACCOUNTS` | The company's Workspace domain, e.g. `company.com` |
| `TOKEN_ENCRYPTION_KEY` and client secrets | New values, kept in the host's secret store. Never reuse the local ones. |
| Hosting | Serve the frontend and backend on one host (e.g. a reverse proxy), so the session cookie reaches both. |

## 1.7 Check it works

From the repo root:

- **Tests:** see [DEVELOPMENT.md §3](../DEVELOPMENT.md#3-unit-tests). ✅ All pass, with no real API calls.
- **Tokens are encrypted at rest:**
  ```
  docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "select provider, left(encode(access_token,'escape'),6) from connections;"
  ```
  ✅ The token column shows `gAAAAA` (ciphertext), never a raw token.
- **Disconnect:** click **Disconnect**. ✅ The tool shows **Connect** again, and the app is gone from https://myaccount.google.com/permissions.
- **Log out:** at http://localhost:8000/docs, run **`DELETE /api/session`**. ✅ **Test** now returns `401`.

## Troubleshooting

| You see | Fix |
|---|---|
| `503 … set <VAR>` | Add `<VAR>` to `backend/.env`, then restart |
| `?error=invalid_state` | Start again from **Connect**. Don't refresh the callback page. |
| `?error=provider_error` | The redirect URI doesn't match exactly; or for Google, the account isn't a test user or isn't in `GOOGLE_ALLOWED_ACCOUNTS` |
| `?error=account_mismatch` | That account belongs to another user, or you're signed in as someone else: log out first |
| `?error=access_denied` | You clicked Cancel on the tool's sign-in page |
| `401 … connect again` | The tool rejected the saved access: connect again |

# Part 2. Development

## 2.1 How it fits

1. **Connect.** A user clicks **Connect** and signs in to the tool. The `connections` table stores their tokens, encrypted. The first connect creates the user (linked by email) and signs them in to the app: the same session as the rest of the API.
2. **Call.** Backend code calls the tool as that user (`store.*`), or as the admin for sync (`atlassian`, `drive`, `slack`).
3. **Permissions.** Each connection writes the user's principals (2.4) to `user_principals`. Search keeps the documents whose `acl` overlaps them (`app/auth/principals.py`). Then the live check re-asks the tool, and has the final say.

Code: `backend/app/connectors/`. Users, sessions and principals are in `backend/app/auth/`. Connectors depend on auth, never the reverse.

## 2.2 HTTP API

Auth is the `ib_session` cookie (HttpOnly, 12 hours), set on first connect. Routes marked "user" return `401 {"detail": "Not signed in"}` without it.

- `{id}`: `drive`, `slack`, `jira` or `confluence`
- `{provider}`: `google`, `slack` or `atlassian`
- Unknown values return `404`.

| Request | Auth | Response | Errors |
|---|---|---|---|
| `GET /connectors` | optional | `200` list (below). All `connected: false` if signed out. | none |
| `GET /connectors/{id}/connect` | none | `302` to the tool's sign-in page | `503 "<provider> sign-in is not configured: set <VAR>"` |
| `GET /oauth/{provider}/callback` | none (called by the tool) | `303` to `{FRONTEND_URL}/connectors?connected=<provider>` | `303` to `…?error=access_denied`, `provider_error`, `invalid_state` or `account_mismatch` |
| `GET /connectors/{id}/ping` | user | `200 {"ok": true, "as": "<name or email>"}` | `404` not connected, `401` connect again, `502` tool API failed |
| `DELETE /connectors/{id}` | user | `204`. Also revokes the grant at Google or Slack. Jira and Confluence share one sign-in, so this disconnects both. | none |
| `DELETE /api/session` | optional | `204`, and clears the cookie (log out; `app/api/routes.py`) | none |

`GET /connectors` response:
```json
[
  {"id": "drive", "name": "Google Drive", "connected": true,
   "account": {"name": "<display name>", "email": "<email>"}},
  {"id": "slack", "name": "Slack", "connected": false, "account": null}
]
```

Errors use FastAPI's shape, `{"detail": "<message>"}`. Every route is also listed at http://localhost:8000/docs.

## 2.3 Python API

Use these inside FastAPI handlers. `user` is the app user's id (`int`).

```python
from fastapi import Depends, HTTPException
from app.api.deps import current_user           # 401 if not signed in
from app.auth.session import User
from app.db import Db                           # SQLAlchemy Engine
from app.connectors import atlassian, store

@router.get("/example")
def example(engine: Db, current: User = Depends(current_user)):
    user = current.id
    try:
        channels = store.slack_client(engine, user).conversations_list(types="public_channel,private_channel")
        with store.atlassian_client(engine, user, "jira") as jira:
            issues = atlassian.request("POST", "/rest/api/3/search/jql", http=jira, json={"jql": "order by updated"}).json()
    except store.NotConnected as e:
        raise HTTPException(404, "not connected") from e
    except store.ReconnectNeeded as e:
        raise HTTPException(401, "connect again") from e
```

**As the signed-in user** (`store.py`). Tokens are refreshed automatically.

| Function | Returns |
|---|---|
| `store.slack_client(engine, user)` | slack_sdk `WebClient` |
| `store.drive_service(engine, user)` | Drive v3 service (`googleapiclient`). Call `.execute(num_retries=3)` on each request. |
| `store.google_credentials(engine, user)` | google-auth `Credentials`, for `drive.can_read` |
| `store.atlassian_client(engine, user, "jira" \| "confluence")` | `httpx.Client` for that product. Use it in a `with` block, through `atlassian.request(..., http=client)`. |

Every function above raises:
- `store.NotConnected` if the user hasn't connected that tool (or their Atlassian site lacks that product)
- `store.ReconnectNeeded` if the tool revoked the access

**As the admin** (for sync; set up in 1.5):

| Function | Returns |
|---|---|
| `atlassian.request(method, path, http=None, **httpx_kwargs)` | `httpx.Response`. It uses the admin client when `http` is omitted, retries 429/5xx, and raises `httpx.HTTPStatusError` on other errors. |
| `drive.service(drive.admin_credentials())` | Drive v3 service as the admin |
| `slack.bot()` | slack_sdk `WebClient` as the workspace bot |

**Permissions:**

| Function | Input | Returns |
|---|---|---|
| `principals_for(conn, user)` (`app/auth/principals.py`) | an open connection | The ACL entries the user holds (2.4), from `user_principals`, plus `public` |
| `drive.can_read(credentials, file_ids)` | `store.google_credentials(...)`, Drive file IDs | IDs the user can read right now (one batched call per 100 files) |
| `slack.can_read(slack_user_id, channel_ids)` | the user's Slack ID (`connections.account_id`), channel IDs | IDs the user can read right now (checked with the bot) |

Both `can_read` functions deny by default: any error leaves the ID out. Jira and Confluence live checks don't exist yet.

**Rules:**
- Pass `engine`, not an open connection, to the `store.*` client functions: they commit token refreshes in their own short transaction.
- Never send tokens or raw tool errors to the browser.
- Don't add retry loops: the clients above already retry rate limits.

## 2.4 Document schema (sync contract)

Sync isn't built yet. When it is, every source will write one `documents` row (with its `chunks`) per Drive file, Slack thread, Jira ticket or Confluence page. Tables: `migrations/versions/0002_core_schema.py`; contract: [QUERY_PIPELINE.md](../architecture/QUERY_PIPELINE.md). The shape:

```jsonc
{
  "source": "drive",                      // drive | slack | jira | confluence
  "source_id": "<id in the tool>",
  "title": "<title>",
  "text": "<plain text>",
  "url": "<link that opens it in the tool>",
  "updated_at": "2026-10-01T05:00:00Z",   // UTC
  "metadata": {},                         // optional, per source
  "acl": ["google:user:<email>", "public"]
}
```

`acl` entries, the same strings connections write to `user_principals`:

| Principal | Meaning |
|---|---|
| `google:user:<email>` | That Google user (emails in lower case) |
| `google:domain:<domain>` | Everyone with a verified email on that domain |
| `slack:user:<slack user id>` | That Slack user (private channels) |
| `slack:members` | Every full member of the workspace (public channels). Guests never hold it. |
| `atlassian:user:<accountId>` | That Atlassian user. Groups and roles are expanded into users. |
| `public` | Anyone: a Drive file shared with "anyone", or a ticket every Jira user can see. Held by every user (`principals_for`). |

An `acl` may include extra people but never leaves out a real reader: `can_read` removes the extras.

Field mappings per source are in §5 of [GOOGLE_DRIVE.md](GOOGLE_DRIVE.md), [SLACK.md](SLACK.md), [JIRA.md](JIRA.md) and [CONFLUENCE.md](CONFLUENCE.md).

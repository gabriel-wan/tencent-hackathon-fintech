# Connectors guide

## 1. Introduction

Users connect their own Google Drive, Slack, Jira and Confluence accounts. The backend then calls each tool as that user.

The team shares one workspace per tool, so everyone sees the same data. Each developer connects with their own account, on their own laptop.

| Tool | Set up once, by one teammate | Each developer |
|---|---|---|
| Google Drive (3) | One Google Cloud project with a shared sign-in app | Is added as a test user, then connects |
| Slack (4) | One Slack workspace | Creates their own Slack app and pastes its token |
| Jira and Confluence (5) | One Atlassian site | Creates their own Atlassian app, then connects |

**Order:** do section 2 first. Sections 3 to 5 are independent: do only the tools you need. Section 6 is for deploying. Section 7 is for writing code.

**Rules:**
- `<angle brackets>` are placeholders. Replace them, brackets included.
- Real values go only in `backend/.env`, which git ignores. Never put them in `.env.example`, code, docs, chat or screenshots. If `git status` ever lists `.env`, stop and ask.
- Send shared values through the team's password manager.
- Always open the app at `localhost`, never `127.0.0.1`, and don't change the ports. Sign-in only works on `localhost:8000`.

## 2. Basics (each developer)

**Setting a variable:** most variables in `backend/.env` start commented out (`# NAME=`). To set one, delete the `# ` and put the value after `=`.

**Restarting:** in the terminal running Docker, press Ctrl+C, then run `docker compose up`. A `.env` change applies only after a restart.

1. Install the prerequisites in [DEVELOPMENT.md §1](../DEVELOPMENT.md#1-get-started-locally).
2. From the repo root, copy `backend/.env.example` to `backend/.env`, and `frontend/.env.example` to `frontend/.env`. The frontend file needs no changes.
3. From `backend/`, generate your encryption key (it encrypts stored tokens):
   ```
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
4. In `backend/.env`, set `TOKEN_ENCRYPTION_KEY=<the printed key>`, including its trailing `=`.
5. From the repo root, run `docker compose up --build`. When it's running, open http://localhost:3000/connectors.
   - ✅ The 4 tools are listed. **Connect** on a tool you haven't set up returns 503, naming the missing variable.

Each tool row has **Connect**, **Test** and **Disconnect**. **Test** opens `{"ok": true, "as": "<your name or email>"}` when the connection works, or says `connect again` when it doesn't.

## 3. Google Drive

**Set up once (one teammate):**
1. Go to https://console.cloud.google.com. In the project picker (top left), click **New project**, name it e.g. `<project> (dev)`, and click **Create**. Make sure it's selected.
2. Open **APIs & Services → Library** (left menu). Search for **Google Drive API**, open it, and click **Enable**.
3. Open **Google Auth Platform** (search bar), and click **Get started**. Fill in:
   - **App information:** any name; your email as the support email
   - **Audience:** External
   - **Contact information:** your email

   Agree to the policy, then click **Create**.
4. Click **Audience** (left menu). Under **Test users**, click **Add users**, add every developer's Google email (at most 100), and save. Leave the status as **Testing**.
5. Click **Clients** (left menu), then **Create client**. Set **Application type** to **Web application**. Under **Authorized redirect URIs**, click **Add URI** and enter `http://localhost:8000/oauth/google/callback`. Click **Create**.
6. The dialog shows the **Client ID** and **Client secret**. Send both to the team. (They're also under **Clients →** your client later.)

**Each developer:**
1. Send your Google email to the teammate above, and wait until you're added as a test user.
2. In `backend/.env`, set:
   ```
   GOOGLE_CLIENT_ID=<Client ID>
   GOOGLE_CLIENT_SECRET=<Client secret>
   GOOGLE_ALLOWED_ACCOUNTS=<your Google email>
   ```
3. Restart. Open http://localhost:3000/connectors, click **Connect** on Google Drive, and sign in with that Google account. At "Google hasn't verified this app", click **Continue**, then allow access.
   - ✅ Drive shows your email, and **Test** shows it too.

In Testing mode, Google ends the access after 7 days. When **Test** says `connect again`, click **Connect** again.

## 4. Slack

Locally, you connect Slack by pasting a token from your own Slack app. The **Connect** button only works in production, because Slack only redirects to `https://` addresses.

**Set up once (one teammate):**
1. Create a Slack workspace for the project (or pick an existing one), and invite every developer.
2. Open it at https://app.slack.com. The address bar shows `https://app.slack.com/client/T…/…`. Copy the part starting with `T` (e.g. `T0123ABCD`): that's the workspace ID.
3. Send the workspace ID to the team.

**Each developer:**
1. Go to https://api.slack.com/apps. Click **Create New App → Blank app**, name it e.g. `<project> dev (<your name>)`, pick the team's workspace, and create it.
2. Click **OAuth & Permissions** (left menu) and scroll to **Scopes**. Under **User Token Scopes** (not Bot Token Scopes), click **Add an OAuth Scope** once for each: `channels:read`, `channels:history`, `groups:read`, `groups:history`, `users:read`, `users:read.email`. Leave **Required** unticked.
3. Scroll back to the top of **OAuth & Permissions**. Click **Install to Workspace**, then **Allow**. (If the workspace requires admin approval, ask its admin to approve your app first.)
4. Copy the **User OAuth Token** (`xoxp-…`) that now appears. It acts as you: never share it.
5. In `backend/.env`, set `SLACK_TEAM_ID=<the workspace ID>`. Restart.
6. Open http://localhost:3000/connectors. Paste your `xoxp-…` token into the Slack box and click **Connect with token**.
   - ✅ The page says "Connected to slack", and Slack shows your email. **Test** shows your Slack name.

## 5. Jira and Confluence

One Atlassian sign-in connects both. The team shares one Atlassian site. Each developer creates their own private sign-in app, because a shared app needs Atlassian's Personal Data Reporting API, which isn't built (section 6).

**Set up once (one teammate, a site admin):**
1. Go to https://admin.atlassian.com. Open **Users** (left menu), click **Invite users**, and invite every developer with access to Jira and Confluence.
2. Open Jira. The address bar shows `https://<site>.atlassian.net/…`: that's the site address.
3. Open `https://<site>.atlassian.net/_edge/tenant_info`. It shows `{"cloudId":"…"}`. Copy that value, without quotes: it's the site's cloud ID.
4. Send the site address and the cloud ID to the team.

**Each developer:**
1. Accept the invite email. Open the site address and check you can see Jira and Confluence.
2. Go to https://developer.atlassian.com/console/myapps, signed in with that same Atlassian account. Click **Create → OAuth 2.0 integration**, name it e.g. `<project> dev (<your name>)`, accept the terms, and click **Create**. Your app opens.
3. Click **Authorization** (left menu). Next to **OAuth 2.0 (3LO)**, click **Add**. Set **Callback URL** to `http://localhost:8000/oauth/atlassian/callback`, and click **Save changes**.
4. Click **Permissions** (left menu). For each API below, click **Add** next to it, then **Configure**. Open the **Classic scopes** tab, click **Edit Scopes**, tick the scopes, and save:
   - **Jira API:** `read:jira-work`, `read:jira-user`
   - **Confluence API:** `read:confluence-content.all`, `read:confluence-space.summary`, `search:confluence`, `read:confluence-user`
   - **User identity API:** `read:me`
5. Skip **Distribution**: leave it as **Not sharing**.
6. Click **Settings** (left menu). Under **Authentication details**, copy the **Client ID** and **Secret** into `backend/.env`, along with the team's cloud ID:
   ```
   ATLASSIAN_CLIENT_ID=<Client ID>
   ATLASSIAN_CLIENT_SECRET=<Secret>
   ATLASSIAN_CLOUD_ID=<the team's cloud ID>
   ```
   The long ID in this page's address is your app's ID, not the cloud ID.
7. Restart. Open http://localhost:3000/connectors, click **Connect** on Jira, sign in with the same Atlassian account, then click **Accept**.
   - ✅ Jira and Confluence both show connected, and **Test** on each shows your name.

## 6. Production

Production uses its own apps and secrets, never the ones from your laptop. `<APP_URL>` below is the public `https://` address of the backend.

1. **Host.** Serve the frontend and backend on one `https://` domain (e.g. behind a reverse proxy), so the session cookie reaches both.
2. **Secrets.** Generate a new `TOKEN_ENCRYPTION_KEY` (section 2, step 3). Keep it and every client secret below in the host's secret store.
3. **Backend variables:**
   ```
   APP_ENV=production
   APP_URL=<APP_URL>
   FRONTEND_URL=<public frontend address>
   ```
4. **Frontend variables:** `APP_ENV=production`, and `BACKEND_LOCAL_URL=<APP_URL>`. This replaces Slack's token box with the **Connect** button.
5. **Google.** Repeat section 3's set-up in a new project, with these changes:
   - **Audience:** **Internal** if the company uses Google Workspace (no review needed). Otherwise **External**, then publish the app, which requires Google's verification for Drive access.
   - **Authorized redirect URI:** `<APP_URL>/oauth/google/callback`
   - Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_ALLOWED_ACCOUNTS=<company domain, e.g. company.com>`.
6. **Slack.** The workspace admin creates one company app, following section 4 steps 1 and 2. Then:
   - **OAuth & Permissions → Redirect URLs:** add `<APP_URL>/oauth/slack/callback`, and save.
   - **Basic Information → App Credentials:** copy the **Client ID** and **Client Secret**.
   - Set `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` and `SLACK_TEAM_ID`.
7. **Jira and Confluence: blocked.** Every user signing in to one company app needs **Distribution → Sharing**. Sharing asks whether the app stores personal data: it does (Atlassian account IDs), so Atlassian requires the [Personal Data Reporting API](https://developer.atlassian.com/cloud/jira/platform/user-privacy-developer-guide/) (report stored account IDs every 7 days, erase data for closed accounts). Build it first, and never tick its confirmation box before then.
8. Deploy. Open `<public frontend address>/connectors`, and click **Connect** on each tool.
   - ✅ **Test** shows your account on each.

## 7. Development

### 7.1 How it fits

1. **Connect.** A user clicks **Connect** and signs in to the tool. The `connections` table stores their tokens, encrypted. The first connect creates the user (linked by email) and signs them in to the app: the same session as the rest of the API.
2. **Call.** Backend code calls the tool as that user (`store.*`), or as the admin for sync (`atlassian`, `drive`, `slack`).
3. **Permissions.** Each connection writes the user's principals (7.4) to `user_principals`. Search keeps the documents whose `acl` overlaps them (`app/auth/principals.py`). Then the live check re-asks the tool, and has the final say.

Code: `backend/app/connectors/`. Users, sessions and principals are in `backend/app/auth/`. Connectors depend on auth, never the reverse.

### 7.2 HTTP API

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
| `POST /api/dev/connectors/slack` | none. **Development only** | `{"token": "xoxp-…"}`: connects Slack like **Connect**, starts a session. `200 {"connected": "slack", "as": "<name>"}` | `400` token rejected or other workspace, `409` account belongs to someone else, `503` not configured |

`GET /connectors` response:
```json
[
  {"id": "drive", "name": "Google Drive", "connected": true,
   "account": {"name": "<display name>", "email": "<email>"}},
  {"id": "slack", "name": "Slack", "connected": false, "account": null}
]
```

Errors use FastAPI's shape, `{"detail": "<message>"}`. Every route is also listed at http://localhost:8000/docs.

### 7.3 Python API

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

**As the admin** (for sync; set up in 7.5):

| Function | Returns |
|---|---|
| `atlassian.request(method, path, http=None, **httpx_kwargs)` | `httpx.Response`. It uses the admin client when `http` is omitted, retries 429/5xx, and raises `httpx.HTTPStatusError` on other errors. |
| `drive.service(drive.admin_credentials())` | Drive v3 service as the admin |
| `slack.bot()` | slack_sdk `WebClient` as the workspace bot |

**Permissions:**

| Function | Input | Returns |
|---|---|---|
| `principals_for(conn, user)` (`app/auth/principals.py`) | an open connection | The ACL entries the user holds (7.4), from `user_principals`, plus `public` |
| `drive.can_read(credentials, file_ids)` | `store.google_credentials(...)`, Drive file IDs | IDs the user can read right now (one batched call per 100 files) |
| `slack.can_read(slack_user_id, channel_ids)` | the user's Slack ID (`connections.account_id`), channel IDs | IDs the user can read right now (checked with the bot) |

Both `can_read` functions deny by default: any error leaves the ID out. Jira and Confluence live checks don't exist yet.

**Rules:**
- Pass `engine`, not an open connection, to the `store.*` client functions: they commit token refreshes in their own short transaction.
- Never send tokens or raw tool errors to the browser.
- Don't add retry loops: the clients above already retry rate limits.

### 7.4 Document schema (sync contract)

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

### 7.5 Admin credentials (for sync)

Background sync reads as an admin, not as a user. Only needed if you work on sync.

1. Set the admin variables listed in [DEVELOPMENT.md §2](../DEVELOPMENT.md#backend-admin-credentials-background-sync).
2. From the repo root, run:
   ```
   docker compose run --rm --no-deps backend python -m app.connectors
   ```
   - ✅ Each tool prints `OK` and the account it acts as. `FAIL` names the bad setting.

### 7.6 Check it works

Run from the repo root. Replace `<POSTGRES_USER>` and `<POSTGRES_DB>` with the values in your `backend/.env`.

- **Tests:** see [DEVELOPMENT.md §3](../DEVELOPMENT.md#3-unit-tests). ✅ All pass, with no real API calls.
- **Same session as the app:** after connecting, open http://localhost:8000/api/me. ✅ It shows your email.
- **Tokens are encrypted at rest:**
  ```
  docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "select provider, left(encode(access_token,'escape'),6) from connections;"
  ```
  ✅ The token column shows `gAAAAA` (ciphertext), never a raw token.
- **Principals are written:**
  ```
  docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "select * from user_principals;"
  ```
  ✅ After connecting Drive: `google:user:<your email>` and `google:domain:<your domain>`.
- **Outsiders are rejected:** connect with a Google test user that is *not* in `GOOGLE_ALLOWED_ACCOUNTS`. ✅ `?error=provider_error`, and no new row in `users`.
- **Disconnect:** click **Disconnect**. ✅ The tool shows **Connect** again, its rows are gone from `user_principals`, and the app is gone from https://myaccount.google.com/permissions.
- **Log out:** at http://localhost:8000/docs, run **`DELETE /api/session`**. ✅ **Test** now returns `401`.

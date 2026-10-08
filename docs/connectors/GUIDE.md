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

1. Set up and start KnowBuddy: [RUNNING.md](../RUNNING.md) sections 1 to 3 (settings, encryption key, start).
2. Then set up each tool you need, below. Connect **Slack first**: a company starts from a Slack workspace, and the
   first full member to connect it becomes the admin. Who joins which company, and why Atlassian never starts one:
   [RUNNING.md](../RUNNING.md) section 5.
3. Once tools are connected, the admin chooses what KnowBuddy may read and syncs it:
   [RUNNING.md](../RUNNING.md) section 5, step 3.

On **Connections** (`/connectors`), each tool's card has **Connect**, **Test** and **Disconnect**. **Test** says "Works. The tool sees you as <your name or email>." when the connection works, or "Access expired or was revoked. Connect again." when it doesn't. (The backend route behind it, `GET /connectors/{id}/ping`, returns `{"ok": true, "as": "…"}`.)

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
   ```
   Use the same email as on Slack and Jira/Confluence ([RUNNING.md](../RUNNING.md) section 5).
3. Restart. Open http://localhost:3000/connectors, click **Connect** on Google Drive, and sign in with that Google account. At "Google hasn't verified this app", click **Continue**, then allow access.
   - ✅ Drive shows your email, and **Test** shows it too.

In Testing mode, Google ends the access after 7 days. When **Test** says `connect again`, click **Connect** again.

## 4. Slack

Locally, you connect Slack by pasting a token from your own Slack app. The **Connect** button only works in production, because Slack only redirects to `https://` addresses.

**Set up once (one teammate):**
1. Create a Slack workspace for the project (or pick an existing one), and invite every developer as a full member (not a guest).

**Each developer:**
1. Go to https://api.slack.com/apps. Click **Create New App → Blank app**, name it e.g. `<project> dev (<your name>)`, pick the team's workspace, and create it.
2. Click **OAuth & Permissions** (left menu) and scroll to **Scopes**. Under **User Token Scopes** (not Bot Token Scopes), click **Add an OAuth Scope** once for each: `channels:read`, `channels:history`, `groups:read`, `groups:history`, `users:read`, `users:read.email`. Leave **Required** unticked.
3. Scroll back to the top of **OAuth & Permissions**. Click **Install to Workspace**, then **Allow**. (If the workspace requires admin approval, ask its admin to approve your app first.)
4. Copy the **User OAuth Token** (`xoxp-…`) that now appears. It acts as you: never share it.
5. Open http://localhost:3000/login (or **Connections**, if you're already signed in). Paste your `xoxp-…` token into the **Connect Slack with a token** box and click **Connect with token**.
   - ✅ You're signed in, and on **Connections** the Slack card shows your email. **Test** shows your Slack name.

## 5. Jira and Confluence

One Atlassian sign-in connects both. The team shares one Atlassian site. Each developer creates their own private sign-in app, because a shared app needs Atlassian's Personal Data Reporting API, which isn't built (section 6).

**Set up once (one teammate, a site admin):**
1. Go to https://admin.atlassian.com. Open **Users** (left menu), click **Invite users**, and invite every developer with access to Jira and Confluence.
2. Send the site address (`https://<site>.atlassian.net`) to the team.

**Each developer:**
1. Accept the invite email. Open the site address and check you can see Jira and Confluence.
2. Go to https://developer.atlassian.com/console/myapps, signed in with that same Atlassian account. Click **Create → OAuth 2.0 integration**, name it e.g. `<project> dev (<your name>)`, accept the terms, and click **Create**. Your app opens.
3. Click **Authorization** (left menu). Next to **OAuth 2.0 (3LO)**, click **Add**. Set **Callback URL** to `http://localhost:8000/oauth/atlassian/callback`, and click **Save changes**.
4. Click **Permissions** (left menu). For each API below, click **Add** next to it, then **Configure**. On each scopes tab named below, click **Edit Scopes**, tick the scopes, and save:
   - **Jira API**, Classic scopes: `read:jira-work`, `read:jira-user`
   - **Confluence API**, Classic scopes: `read:confluence-content.all`, `search:confluence`, `read:confluence-user`, `read:confluence-groups`
   - **Confluence API**, Granular scopes: `read:space:confluence`, `read:page:confluence` (Confluence's newer v2 API accepts only these)
   - **User identity API**, Classic scopes: `read:me`
5. Skip **Distribution**: leave it as **Not sharing**.
6. Click **Settings** (left menu). Under **Authentication details**, copy the **Client ID** and **Secret** into `backend/.env`:
   ```
   ATLASSIAN_CLIENT_ID=<Client ID>
   ATLASSIAN_CLIENT_SECRET=<Secret>
   ```
7. Restart. Open http://localhost:3000/connectors, click **Connect** on Jira, sign in with the same Atlassian account, then click **Accept**.
   - ✅ Jira and Confluence both show connected, and **Test** on each shows your name.
   - Connected before the Confluence scopes changed (the two granular ones, and `read:confluence-groups`)? Add them to your app (step 4), then click **Connect** again. Atlassian refuses the whole sign-in ("Something went wrong") if any requested scope isn't ticked.

## 6. Production

Production uses its own apps and secrets, never the ones from your laptop. `<APP_URL>` below is the public `https://` address of the backend.

1. **Host.** Serve the frontend and backend on one `https://` domain (e.g. behind a reverse proxy), so the session cookie reaches both.
2. **Secrets.** Generate a new `TOKEN_ENCRYPTION_KEY` ([RUNNING.md](../RUNNING.md) section 2). Keep it and every client secret below in the host's secret store.
3. **Backend variables:**
   ```
   APP_ENV=production
   APP_URL=<APP_URL>
   FRONTEND_URL=<public frontend address>
   ```
4. **Frontend variables:** `BACKEND_LOCAL_URL=<APP_URL>`. The Slack token box disappears by itself, because the backend's development routes don't exist with `APP_ENV=production`.
5. **Google.** Repeat section 3's set-up in a new project, with these changes:
   - **Audience:** **Internal** if the company uses Google Workspace (no review needed). Otherwise **External**, then publish the app, which requires Google's verification for Drive access.
   - **Authorized redirect URI:** `<APP_URL>/oauth/google/callback`
   - Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Serving many companies needs **External**, published and verified: Drive is a restricted scope, so Google's verification includes a security assessment and takes weeks.
6. **Slack.** Create one app for the product, following section 4 steps 1 and 2. Then:
   - **OAuth & Permissions → Redirect URLs:** add `<APP_URL>/oauth/slack/callback`, and save.
   - **Basic Information → App Credentials:** copy the **Client ID** and **Client Secret**.
   - **Manage Distribution:** activate public distribution, so other companies' workspaces can install it.
   - Set `SLACK_CLIENT_ID` and `SLACK_CLIENT_SECRET`.
7. **Jira and Confluence: blocked.** Every user signing in to one company app needs **Distribution → Sharing**. Sharing asks whether the app stores personal data: it does (Atlassian account IDs), so Atlassian requires the [Personal Data Reporting API](https://developer.atlassian.com/cloud/jira/platform/user-privacy-developer-guide/) (report stored account IDs every 7 days, erase data for closed accounts). Build it first, and never tick its confirmation box before then.
8. **Companies** sign themselves up: the first full member to connect Slack from a new workspace creates the company and becomes its admin ([RUNNING.md](../RUNNING.md) section 5).
9. Deploy. The `sync` service (`docker-compose.yml`) syncs every company every 5 minutes. Open `<public frontend address>/connectors`, and click **Connect** on each tool.
   - ✅ **Test** shows your account on each.

## 7. Development

### 7.1 How it fits

1. **Connect.** A user clicks **Connect** and signs in to the tool. The `connections` table stores their tokens, encrypted. The first connect creates the user (linked by email) and signs them in to the app: the same session as the rest of the API.
2. **Sync.** Every 5 minutes (or on **sync now**), `app/sync.py` reads each boundary scope as the company admin's own connection and writes `documents` and `chunks` (7.4, 7.5).
3. **Permissions.** Each connection writes the user's principals (7.4) to `user_principals`. Search keeps the user's own company's documents whose `acl` overlaps them (`app/auth/principals.py`). Then the live check re-asks each tool as that user (`app/connectors/live.py`), and has the final say.

Code: `backend/app/connectors/` (one module per source, each with `scopes`, `fetch` and `can_read`), `backend/app/sync.py`, `backend/app/companies.py`. Users, sessions and principals are in `backend/app/auth/`. Connectors depend on auth, never the reverse.

### 7.2 HTTP API

Auth is the `ib_session` cookie (HttpOnly, 12 hours), set on first connect. Routes marked "user" return `401 {"detail": "Not signed in"}` without it.

- `{id}`: `drive`, `slack`, `jira` or `confluence`
- `{provider}`: `google`, `slack` or `atlassian`
- Unknown values return `404`.

| Request | Auth | Response | Errors |
|---|---|---|---|
| `GET /connectors` | optional | `200` list (below). All `connected: false` if signed out. | none |
| `GET /connectors/{id}/connect` | none | `302` to the tool's sign-in page | `503 "<provider> sign-in is not configured: set <VAR>"` |
| `GET /oauth/{provider}/callback` | none (called by the tool) | `303` to `{FRONTEND_URL}/connectors?connected=<provider>` | `303` to `…?error=access_denied`, `provider_error`, `no_company`, `missing_permission` (Google sign-in without Drive ticked), `invalid_state` or `account_mismatch` |
| `GET /connectors/{id}/ping` | user | `200 {"ok": true, "as": "<name or email>"}` | `404` not connected, `401` connect again, `502` tool API failed |
| `DELETE /connectors/{id}` | user | `204`. Also revokes the grant at Google or Slack. Jira and Confluence share one sign-in, so this disconnects both. | none |
| `DELETE /api/session` | optional | `204`, and clears the cookie (log out; `app/api/routes.py`) | none |
| `GET /api/admin/scopes/{id}` | admin | `200 [{"id", "title"}]`: channels, folders, projects or spaces the admin can see | `403` not an admin, `404` not connected |
| `GET /api/admin/boundary` | admin | `200` your company's boundary | `403` |
| `PUT /api/admin/boundary/{id}/{scope_id}` | admin | `{"title": "<name>"}` → `204`. Audited. | `403`, `404` unknown tool |
| `DELETE /api/admin/boundary/{id}/{scope_id}` | admin | `204`; its documents are hidden at once. Audited. | `403`, `404` |
| `POST /api/admin/sync` | admin | `202`: syncs your company now, in the background | `403` |
| `GET /api/admin/audit` | admin | `200 {"records": [...], "next_before_id"}`: your company's audit trail, newest first; filters `user`, `since`, `until`, `event_type`, `document`, `source`, `scope_id`, `before_id`, `limit` (ADR-007) | `403`, `422` bad filter |
| `POST /api/admin/audit/verify` | admin | `200 {"ok", "checked", "first_broken_id", "reason", "head"}`: recomputes your company's hash chain | `403` |
| `POST /api/dev/connectors/slack` | none. **Development only** | `{"token": "xoxp-…"}`: connects Slack like **Connect**, starts a session. `200 {"connected": "slack", "as": "<name>"}` | `400` token rejected, `403 no_company` workspace belongs to no company you can join, `409` account belongs to someone else, `503` not configured |

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
        channels = store.client(engine, user, "slack").conversations_list(types="public_channel,private_channel")
        with store.client(engine, user, "jira") as jira:
            issues = atlassian.request("POST", "/rest/api/3/search/jql", http=jira, json={"jql": "order by updated"}).json()
    except store.NotConnected as e:
        raise HTTPException(404, "not connected") from e
    except store.ReconnectNeeded as e:
        raise HTTPException(401, "connect again") from e
```

**As the signed-in user** (`store.py`). Tokens are refreshed automatically.

`store.client(engine, user, source)` returns the API client for `source`:

| `source` | Returns |
|---|---|
| `slack` | slack_sdk `WebClient` |
| `drive` | Drive v3 service (`googleapiclient`). Call `.execute(num_retries=3)` on each request. |
| `jira`, `confluence` | `httpx.Client` for that product. Use it in a `with` block, through `atlassian.request(..., http=client)`, which retries 429/5xx and raises `httpx.HTTPStatusError` on other errors. |

It raises:
- `store.NotConnected` if the user hasn't connected that tool (or their Atlassian site lacks that product)
- `store.ReconnectNeeded` if the tool revoked the access

**Each source module** (`store.SOURCES[source]`: `slack`, `drive`, `jira`, `confluence`) takes a client from `store.client`:

| Function | Returns |
|---|---|
| `scopes(client)` | `[{"id", "title"}]`: channels, folders, projects or spaces that person can see |
| `fetch(client, scope_id, changed)` | the scope's documents (7.4), with ACLs. Text is downloaded only when `changed(source_id, updated_at)`; otherwise `text` is `None` |
| `can_read(client, ids)` | the `source_id`s that person can read right now. Denies by default: any error leaves the ID out. |

**Permissions:** `principals_for(conn, user)` (`app/auth/principals.py`) returns the ACL entries the user holds (7.4), from `user_principals`, plus `public`. The query pipeline's live check is `app/connectors/live.py`: it finds the asking user's connection from their principal and calls `can_read` as them.

**Rules:**
- Pass `engine`, not an open connection, to the `store.*` client functions: they commit token refreshes in their own short transaction.
- Never send tokens or raw tool errors to the browser.
- Don't add retry loops: the clients above already retry rate limits.

### 7.4 Document schema (sync contract)

Each source's `fetch` yields one document per Drive file, Slack thread, Jira ticket or Confluence page, and `app/sync.py` writes it as one `documents` row (with its `chunks`) for the company. Tables: `migrations/versions/0002_core_schema.py` and `0005_companies.py`; contract: [QUERY_PIPELINE.md](../architecture/QUERY_PIPELINE.md). The shape:

```jsonc
{
  "source": "drive",                      // drive | slack | jira | confluence
  "source_id": "<id in the tool>",        // Slack "<channel>:<ts>", Jira the numeric issue ID; unique per company
  "scope_id": "<boundary scope>",         // channel, top folder, project key or space ID
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
| `public` | Anyone in the company: a Drive file shared with "anyone", or an unrestricted Confluence page. Held by every user (`principals_for`); search never crosses companies. |

An `acl` may include extra people but never leaves out a real reader: `can_read` removes the extras. Known widenings, all trimmed by the live check: a Drive group becomes its domain, Jira issue security levels are not applied, Confluence space permissions are not applied.

Not synced yet: Drive files in shared drives (Drive doesn't list their sharing), PDFs and Office files (no text extraction), and Google Docs over Drive's 10 MB export limit. Each is skipped and logged; the rest of the folder still syncs.

Field mappings per source are in §5 of [GOOGLE_DRIVE.md](GOOGLE_DRIVE.md), [SLACK.md](SLACK.md), [JIRA.md](JIRA.md) and [CONFLUENCE.md](CONFLUENCE.md).

### 7.5 Sync: choose the boundary, then sync

How an admin chooses the boundary and runs a sync: [RUNNING.md](../RUNNING.md) section 5, step 3. Under the
hood, `docker compose up` starts the `sync` service, which repeats it every 5 minutes for every company; you can
also run one sync by hand with `docker compose run --rm backend python -m app.sync`. Chunks are embedded after each
run; if the LLM key is missing or TokenHub is down, keyword search still works and the vectors are filled in on a
later run.

### 7.6 Check it works

Checks after connecting (session, encrypted tokens, principals, outsiders refused, revocations, disconnect, sign
out): [TESTING.md](../TESTING.md) section 4, "With your own tools". Unit tests: [TESTING.md](../TESTING.md) section 1.

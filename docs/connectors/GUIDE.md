# Connectors: set up and test

Connect your own Google Drive, Slack, Jira and Confluence accounts and check that they work.

Run commands in PowerShell from the folder named in each step. Values in `<angle brackets>` are placeholders. Put real values only in `backend\.env`, which git ignores. Never paste them into code, docs, chat or screenshots.

## 1. Automated tests (no accounts needed)

From `backend\`:
```
uv sync
uv run pytest
```
✅ `100 passed`

## 2. Run the app (no accounts needed)

1. Generate an encryption key, from `backend\`:
   ```
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. In `backend\.env` (copied from `.env.example`), set:
   ```
   APP_URL=http://localhost:8000
   TOKEN_ENCRYPTION_KEY=<generated key>
   ```
3. From the repo root, run `docker compose up --build`.
4. Check:
   - ✅ http://localhost:8000/health shows `{"db":"ok",...}`
   - ✅ http://localhost:8000/connectors lists 4 connectors, all `"connected": false`
   - ✅ http://localhost:8000/connectors/drive/connect returns 503 naming `GOOGLE_CLIENT_ID`

## 3. Google Drive

### Create the OAuth app
At https://console.cloud.google.com:

1. Create or choose a project (top bar).
2. **APIs & Services → Library**: enable **Google Drive API**.
3. Open **Google Auth Platform** and click **Get started**:
   - **App information:** any app name, and your Gmail as the support email
   - **Audience:** External
   - **Contact information:** your Gmail
   - Agree, then **Create**
4. **Audience → Test users → Add users**: add your Gmail. Leave the status as **Testing**.
5. **Clients → Create client**:
   - Type: **Web application**
   - **Authorized redirect URI:** `http://localhost:8000/oauth/google/callback`
6. In `backend\.env`, set:
   ```
   GOOGLE_CLIENT_ID=<client id>
   GOOGLE_CLIENT_SECRET=<client secret>
   ```

### Connect and check
1. Restart: Ctrl+C, then `docker compose up`.
2. Open http://localhost:8000/connectors/drive/connect and sign in.
   - "Google hasn't verified this app" is expected in Testing mode: click **Continue** and allow Drive access.
   - You end on a "not found" page at `localhost:3000/connectors?connected=google`. That's expected: the frontend page isn't built yet.
3. Check:
   - ✅ http://localhost:8000/connectors shows Drive `"connected": true`, with your name and email
   - ✅ http://localhost:8000/connectors/drive/ping shows `{"ok":true,"as":"<your email>"}`, from a real API call made as you

## 4. Inspect the database

From the repo root, in a second terminal. If you changed them in `.env`, use your own `POSTGRES_USER` and `POSTGRES_DB` in place of `brain`.

1. Tokens are encrypted at rest:
   ```
   docker compose exec db psql -U brain -d brain -c "select provider, account_email, left(encode(access_token,'escape'),6) as token from connections;"
   ```
   ✅ The token column shows `gAAAAA` (Fernet ciphertext), never a raw token.

2. What search will match you against (`store.principals`):
   ```
   docker compose exec backend python -c "from app.db import engine; from app.auth import users; from app.connectors import store; import sqlalchemy as sa; c = engine.connect(); print(store.principals(c, c.execute(sa.select(users.c.id)).scalar()))"
   ```
   ✅ Something like `{'google:user:<your email>', 'google:domain:<your domain>', 'public'}`

## 5. Disconnect and log out

In http://localhost:8000/docs (same browser, so your session is used):

1. **`DELETE /connectors/{connector}`** → Try it out → `drive` → Execute.
   - ✅ The response is `204`, and `/connectors` shows Drive `false`.
   - ✅ The app no longer appears at https://myaccount.google.com/permissions.
2. **`POST /logout`** → Execute.
   - ✅ The response is `204`, and `/connectors/drive/ping` now returns `401`.

## 6. Slack (optional)

Slack accepts only `https` redirect URIs, so you need a tunnel locally.

1. Start a tunnel with `cloudflared tunnel --url http://localhost:8000`, and note the `https://<tunnel>` address it prints.
2. In `backend\.env`, set `APP_URL=https://<tunnel>`.
3. At https://api.slack.com/apps: **Create New App → From scratch**, in your test workspace.
4. **OAuth & Permissions**:
   - **Redirect URL:** `https://<tunnel>/oauth/slack/callback`
   - **User Token Scopes:** `channels:read`, `channels:history`, `groups:read`, `groups:history`, `users:read`, `users:read.email`
5. In `backend\.env`, set:
   ```
   SLACK_CLIENT_ID=<from Basic Information>
   SLACK_CLIENT_SECRET=<from Basic Information>
   SLACK_TEAM_ID=<the T… part of app.slack.com/client/T…/>
   ```
6. Restart, then open `https://<tunnel>/connectors/slack/connect`.
7. Check:
   - ✅ `/connectors/slack/ping` shows your Slack name.
   - If you also connected Google with the same email, both connections belong to one user.

The tunnel address changes on every run: update `APP_URL` and the Slack redirect URL each time.

## 7. Jira and Confluence (optional)

1. At https://developer.atlassian.com/console: **Create → OAuth 2.0 integration**.
2. **Permissions**: add **Jira API**, **Confluence API** and **User identity API**, with the scopes listed in [backend/README.md](../../backend/README.md#connectors).
3. **Authorization → Callback URL:** `{APP_URL}/oauth/atlassian/callback`
4. In `backend\.env`, set:
   ```
   ATLASSIAN_CLIENT_ID=<from Settings>
   ATLASSIAN_CLIENT_SECRET=<from Settings>
   ATLASSIAN_CLOUD_ID=<cloudId from https://<site>.atlassian.net/_edge/tenant_info>
   ```
5. Restart, then open `{APP_URL}/connectors/jira/connect`.
6. Check:
   - ✅ `/connectors` shows Jira and Confluence both connected, from one sign-in.
   - ✅ `/connectors/jira/ping` and `/connectors/confluence/ping` show your name.

## 8. Admin credentials (optional)

Fill in the admin variables ([DEVELOPMENT.md §2](../DEVELOPMENT.md#2-environment-variables)), then from the repo root run:
```
docker compose run --rm --no-deps backend python -m app.connectors
```
✅ Each tool prints `OK` and the account it acts as. `FAIL` names the missing or wrong setting.

## Troubleshooting

| You see | Fix |
|---|---|
| `503 … set <VAR>` | Add `<VAR>` to `backend\.env`, then restart |
| `?error=invalid_state` | Start again from `/connect`. Don't refresh the callback page. |
| `?error=provider_error` | Redirect URI not an exact match, or (Google) you're not a test user |
| `?error=account_mismatch` | That account belongs to another user, or you're signed in as someone else: log out first |
| `401 … connect again` | The tool rejected the saved access: connect again |
| `No module named 'app.connectors'` | Run tests from `backend\`, not the repo root |

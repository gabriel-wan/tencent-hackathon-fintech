# Setting up the tools

**For:** the teammate setting up a tool's sign-in, and each developer connecting their own accounts.
**You'll:** create the Google, Slack and Atlassian sign-in apps, connect them locally, and set them up for production.
**Not here:** running KnowBuddy → [RUNNING.md](../RUNNING.md) · how connectors work in code →
[architecture/CONNECTORS.md](../architecture/CONNECTORS.md) · each tool's API → [reference/](reference/).

## 1. Introduction

Users connect their own Google Drive, Slack, Jira and Confluence accounts. The backend then calls each tool as that user.

The team shares one workspace per tool, so everyone sees the same data. Each developer connects with their own account, on their own laptop.

| Tool | Set up once, by one teammate | Each developer |
|---|---|---|
| Google Drive (3) | One Google Cloud project with a shared sign-in app | Is added as a test user, then connects |
| Slack (4) | One Slack workspace | Creates their own Slack app and pastes its token |
| Jira and Confluence (5) | One Atlassian site | Creates their own Atlassian app, then connects |

**Order:** do section 2 first. Sections 3 to 5 are independent: do only the tools you need. Section 6 is for deploying. How connectors work in code: [architecture/CONNECTORS.md](../architecture/CONNECTORS.md).

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

How connecting, sync and live checks work in code, the HTTP and Python APIs, and the document format each
connector produces: [architecture/CONNECTORS.md](../architecture/CONNECTORS.md).

# Running KnowBuddy

**For:** anyone running KnowBuddy on their own computer.
**You'll:** start it, sign in, ask questions, and connect your own tools (about 15 minutes for the first part).
**Not here:** testing → [TESTING.md](TESTING.md) · putting it on a server → [connectors/SETUP.md](connectors/SETUP.md) §6 · changing the code → [CONTRIBUTING.md](../CONTRIBUTING.md).

**Contents:** 1. What you need · 2. Settings · 3. Start · 4. Try it with demo personas · 5. Use your own tools ·
6. Using KnowBuddy · 7. Stop, reset, re-seed · 8. When something goes wrong · Appendix: every setting

## 1. What you need

- [Git](https://git-scm.com/) and [Docker Desktop](https://www.docker.com/products/docker-desktop/), running.
  That's all: everything else runs inside Docker.
- Only if you'll edit code outside Docker: [uv](https://docs.astral.sh/uv/getting-started/installation/) for the
  backend and Node.js 24 for the frontend ([CONTRIBUTING.md](../CONTRIBUTING.md) §8). With Homebrew, Node 24 is
  `node@24`, which isn't on your PATH by default: run `export PATH="/opt/homebrew/opt/node@24/bin:$PATH"` in each
  new terminal.

```bash
git clone <repo-url>
cd tencent-hackathon-fintech
```

## 2. Settings

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`.env` files hold secrets and are never committed. The frontend file needs no changes. Some settings in
`backend/.env` start commented out (`# NAME=`): to set one, delete the `# ` and put the value after `=`. Set these
four; everything else already has a working value:

| Setting | What to put |
|---|---|
| `POSTGRES_PASSWORD` | Any password, for your local database's owner account |
| `APP_DB_PASSWORD` | A **different** password: the app's own database login, which can't change audit records |
| `TOKEN_ENCRYPTION_KEY` | A key that encrypts stored sign-in tokens. Generate one (the first run builds the backend image, about a minute): `docker compose run --rm --no-deps backend python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, and paste it including the trailing `=` |
| `LLM_API_KEY` | Your Tencent Cloud TokenHub key (TokenHub console → API Key). It must be allowed to use both models in `.env.example` (Access Scope) |

The full list of settings is in the [appendix](#appendix-every-setting).

## 3. Start

```bash
docker compose up --build
```

This starts five services:

| Service | What it does |
|---|---|
| `db` | PostgreSQL with pgvector: all data, permissions and the audit log |
| `migrate` | Creates or updates the database tables, then exits |
| `backend` | The API, on http://localhost:8000 (every route, with "Try it out": http://localhost:8000/docs) |
| `sync` | Copies each company's chosen content from its tools every 5 minutes |
| `frontend` | The website, on http://localhost:3000 |

✅ http://localhost:3000/status shows `db: ok`.

After editing code, run `docker compose up --build` again. After editing `.env`, recreate the services that read it:
`docker compose up -d --force-recreate backend sync`.

## 4. Try it with demo personas

No accounts needed. Load two fictional companies:

```bash
docker compose run --rm backend python -m app.seed
```

The seed only runs with `APP_ENV=development`. Add `--embed` to also compute embeddings through TokenHub, so
search matches by meaning as well as by keyword.

Open http://localhost:3000/login and pick a person under **Sign in as a seeded user** (development only; identity
isn't checked). Personas have no real connections, so their questions are checked against the stored permissions.

| Persona | Company | Can see | Can't see |
|---|---|---|---|
| Alice, payments engineer | MerlionPay | `#payments-oncall`, `#eng`, the on-call runbook, the contractor guide | `#security-incidents`, the Q3 incident report |
| Ben, backend engineer | MerlionPay | `#eng`, the runbook, the contractor guide | `#payments-oncall`, the security channel and report |
| Charlie, external contractor | MerlionPay | Only the contractor onboarding guide | Everything else |
| Priya, admin and compliance | MerlionPay | Everything in MerlionPay's boundary; the admin pages | Nothing in the boundary is hidden from her |
| Dana, engineer | Kopi Labs | Kopi Labs' `#general` | Anything of MerlionPay |

Nobody sees the "Salary bands" file: its folder is outside MerlionPay's boundary.

Try these:

| As | Ask | You should see |
|---|---|---|
| Alice | What's blocking the payment gateway migration? | An answer citing `#payments-oncall` |
| Charlie | What happened in the Q3 security incident? | "I could not find this in the sources you have access to." |
| Dana | What's blocking the payment gateway migration? | Kopi Labs' own answer (no blockers), never MerlionPay's |

✅ Alice gets an answer with sources, Charlie gets "not found", and Dana never sees MerlionPay content.
More cases: [TESTING.md](TESTING.md) §4.

## 5. Use your own tools

You can also sign in with your real accounts. Do this in a fresh browser session: if you're signed in as a persona,
sign out first, or the sign-in is refused as "already linked to someone else".

**Who becomes admin.** A company starts when the first full member (not a guest) of a new Slack workspace connects
Slack; that person becomes its admin. Google never names a company, and an Atlassian sign-in only joins a company
whose admin has already connected Jira for that site. So connect **Slack first**.

1. **Slack.** Slack's sign-in needs an https address, so locally you paste a token instead: create your own Slack app
   and copy its User OAuth Token (`xoxp-…`) as in [connectors/SETUP.md](connectors/SETUP.md) §4. Paste it in
   **Connect Slack with a token** on http://localhost:3000/login (or on the Connections page once signed in).
2. **Google Drive** and **Jira / Confluence** (optional): each needs a one-time app set-up and two settings in
   `backend/.env`, described in [connectors/SETUP.md](connectors/SETUP.md) §3 and §5. Then click **Connect** on
   http://localhost:3000/connectors. Use the same email address as your Slack account.
3. **Choose what KnowBuddy may read (admin).** Nothing is copied until the admin picks channels, folders, projects
   or spaces: this is the "boundary". The admin pages for it aren't built yet, so use http://localhost:8000/docs
   (you're signed in there too):
   1. Run **`GET /api/admin/scopes/slack`** (or `drive`, `jira`, `confluence`) and note the IDs you want.
   2. For each, run **`PUT /api/admin/boundary/{source}/{scope_id}`** with the body `{"title": "<name>"}`.
   3. Run **`POST /api/admin/sync`** to copy it now instead of within 5 minutes.

   The sync reads as the admin's own accounts, so the admin must be able to open everything they add, including
   being a member of every private channel.
4. **Ask.**

✅ `docker compose logs sync` shows a line like `company 4: slack C0… synced, 5 items, 0 removed`, and a question about that channel is answered with
it as a source.

## 6. Using KnowBuddy

- **Chat (`/`).** Ask one question at a time; each is answered on its own, without the earlier ones. An answer lists
  its sources and a reference number for the audit log. "I could not find this in the sources you have access to"
  means nothing you're allowed to see answers it. It's the same whether the content doesn't exist or you may not see
  it, on purpose.
- **Connections (`/connectors`).** Every tool, whether it's connected, and as whom. **Test** asks the tool who you
  are; **Disconnect** removes the connection (and revokes it at Google or Slack). Jira and Confluence share one
  sign-in, so disconnecting either removes both.
- **Admin pages** (admins only): **Audit** and **Boundary** show a "Not built yet" panel and, in development, a
  design preview filled with labelled MOCK DATA. Their APIs exist and are usable at http://localhost:8000/docs.
- **Development aids:** the persona switcher, the Slack token form, design previews and mock mode exist only when
  the backend runs with `APP_ENV=development`, and are labelled as such on screen.

## 7. Stop, reset, re-seed

| To | Run |
|---|---|
| Stop | Ctrl+C in the terminal running Docker (or `docker compose stop`) |
| Start again | `docker compose up` |
| Re-load the demo data | `docker compose run --rm backend python -m app.seed` (safe to re-run; persona IDs may change) |
| **Wipe the database** | `docker compose down -v`. This deletes all local data: users, connections, documents and the audit log |

## 8. When something goes wrong

| Symptom | Cause and fix |
|---|---|
| The backend exits with "APP_DB_PASSWORD is not set" | Add `APP_DB_PASSWORD` to `backend/.env` (section 2), then `docker compose up -d` |
| Every question says "The assistant isn't available right now" | `LLM_API_KEY` is empty, or the key can't use the models. Fix it, then `docker compose up -d --force-recreate backend sync` |
| Your own tools are connected, but every question says "I could not find this…" | No boundary or no sync yet (section 5, step 3). `docker compose logs sync` shows what was synced |
| **Connect** shows `503 … sign-in is not configured: set GOOGLE_CLIENT_ID` | That tool's app isn't set up: [connectors/SETUP.md](connectors/SETUP.md) §3–5 |
| Sign-in returns with "The sign-in expired or was started in another browser" (`invalid_state`) | You opened `127.0.0.1` instead of `localhost`, or took more than 10 minutes. Start again from http://localhost:3000 |
| "That account is already linked to someone else…" (`account_mismatch`) | You're signed in as someone else (e.g. a persona). Sign out, then connect again |
| "That sign-in belongs to no company you can join" (`no_company`) | You're a Slack guest, the Atlassian site hasn't been added by your company's admin, or you granted several Atlassian sites. Connect Slack first, as a full member |
| "Google Drive access wasn't granted" (`missing_permission`) | Connect again and tick "See and download all your Google Drive files" |
| `docker compose ps` shows `sync` as "unhealthy" | Harmless: it inherits the backend's web health check but has no web server. `docker compose logs sync` shows it working |
| A `.env` change has no effect | `.env` is read when a service starts: `docker compose up -d --force-recreate backend sync` |
| "Cannot connect to the Docker daemon" | Docker Desktop isn't running: start it and wait until it's ready |
| Port 3000 is already in use | Another frontend is running. Stop it, or run the dev server on another port: [frontend/README.md](../frontend/README.md) ("Running") |

Test-specific problems are in [TESTING.md](TESTING.md) §8.

## Appendix: every setting

### Frontend (`frontend/.env`)

| Setting | Value |
|---|---|
| `BACKEND_SERVER_URL` | `http://localhost:8000` (Docker overrides it). Where the frontend's server reaches the backend: the `/api` proxy, server components, `/status` |
| `BACKEND_LOCAL_URL` | `http://localhost:8000`: the backend address your browser uses (the sign-in and Connect links) |
| `NEXT_PUBLIC_API_MOCK` | Optional, development only: `1` fakes chat answers (labelled MOCK DATA). [TESTING.md](TESTING.md) §6 |

The frontend has no development flag of its own: it asks the backend. Development-only controls appear only while
the backend runs with `APP_ENV=development`.

### Backend: basics (`backend/.env`, required)

| Setting | Value |
|---|---|
| `APP_ENV`, `LOG_LEVEL` | `development`, `info`. Development-only routes and the seed need `development` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Any local values; the database is created with them. This is the owner account: only migrations and tests use it |
| `APP_DB_PASSWORD` | Any local value, different from `POSTGRES_PASSWORD`: the app's own database login (`knowbuddy_app`). The `migrate` service sets it on the database on every start |
| `APP_URL` | `http://localhost:8000` |
| `TOKEN_ENCRYPTION_KEY` | Generated as in section 2 |
| `FRONTEND_URL` | Optional. Default `http://localhost:3000` |

### Backend: LLM and embeddings

| Setting | Value |
|---|---|
| `LLM_BASE_URL`, `LLM_MODEL`, `EMBEDDING_MODEL` | Keep the values in `.env.example` (Tencent Cloud TokenHub) |
| `LLM_API_KEY` | TokenHub console → API Key. It must be allowed to use both models (Access Scope) |

### Backend: signing in with your tools

Step by step for each tool: [connectors/SETUP.md](connectors/SETUP.md). In each tool's app settings, register the
redirect address `{APP_URL}/oauth/<google|slack|atlassian>/callback`.

| Setting | Where to get it |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | console.cloud.google.com → APIs & Services → Credentials → OAuth client ID (Web). Enable the Drive API and add test users on the consent screen |
| `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` | api.slack.com/apps → your app → Basic Information. Not needed locally (the token form replaces it) |
| `ATLASSIAN_CLIENT_ID`, `ATLASSIAN_CLIENT_SECRET` | developer.atlassian.com/console → OAuth 2.0 (3LO). Enable the Jira, Confluence and User identity APIs |

Companies aren't a setting: they start from Slack sign-ins (section 5). Sync needs no extra credentials either: it
reads as each company admin's own connections.

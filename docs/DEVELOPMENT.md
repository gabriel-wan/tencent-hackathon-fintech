# Development

## 1. Get started locally

Install [Git](https://git-scm.com/), [Docker Desktop](https://www.docker.com/products/docker-desktop/)
and [uv](https://docs.astral.sh/uv/getting-started/installation/) (uv is for tests and your editor only).

1. Clone the repo, then enter its folder:
   ```
   git clone <repo-url>
   cd tencent-hackathon-fintech
   ```
2. Create the `.env` files ([section 2](#2-environment-variables)).
3. Start everything: `docker compose up --build`
4. Open:
   - http://localhost:3000 for the frontend
   - http://localhost:8000/health for the backend; it returns `{"db": "ok", ...}`
   - http://localhost:8000/docs for every API route, each with "Try it out"

| Task | Command |
|---|---|
| Start | `docker compose up` |
| After editing code | `docker compose up --build` (one service: `docker compose up --build backend`) |
| Stop | Ctrl+C |
| Wipe the database | `docker compose down -v` |

**Backend dependencies (uv).** Dependencies are declared in `backend/pyproject.toml`, and exact versions are locked in `backend/uv.lock`. Run every command below from `backend/`.

| Task | Command |
|---|---|
| Set up, and again after every pull | `uv sync`. It creates `backend/.venv` with Python 3.12 (downloaded if missing) and installs dev tools such as pytest. Select `.venv` as your editor's interpreter. |
| Run anything | `uv run <cmd>`, e.g. `uv run pytest`. No activation needed. For plain `python`, activate first: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (macOS/Linux). |
| Add a package | `uv add <pkg>`, or `uv add --dev <pkg>` for test-only tools |
| Remove a package | `uv remove <pkg>` |
| Upgrade a package | `uv lock --upgrade-package <pkg>`, then `uv sync` |

- Always commit `pyproject.toml` and `uv.lock` together.
- The Docker image installs exactly what `uv.lock` lists, without dev tools (`uv sync --locked --no-dev`). If you edit `pyproject.toml` by hand, run `uv lock` before building, or the build fails.
- Never use `pip install`.

**Database changes:**
- Define the table once, on `app.db.metadata`, in the module that owns it (e.g. `users` in `app/auth.py`).
- Write a numbered migration in `backend/migrations/versions/`, with `down_revision` set to the previous one.
- Check that the migrations match the table definitions: `docker compose run --rm migrate alembic check`.
- If two branches add the same migration number, whoever merges second renumbers theirs.

**Git:** work on a branch, then open a pull request to `main`.

## 2. Environment variables

Copy `backend/.env.example` to `backend/.env`, and `frontend/.env.example` to `frontend/.env`. Never commit `.env` files.

After editing, restart with `docker compose up`. If a setting needed to connect a tool is missing, `/connectors/<tool>/connect` returns 503 naming it.

### Frontend

| Variable | Value |
|---|---|
| `BACKEND_URL` | `http://localhost:8000` (Docker overrides it) |

### Backend: basics (required)

| Variable | Value |
|---|---|
| `APP_ENV`, `LOG_LEVEL` | `development`, `info` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Any local values; the database is created with them |
| `APP_URL` | `http://localhost:8000`. For Slack, use the `https://` address of a tunnel instead (`cloudflared tunnel --url http://localhost:8000`) |
| `TOKEN_ENCRYPTION_KEY` | In `backend/`, run `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `FRONTEND_URL` | Optional. Default `http://localhost:3000` |

### Backend: users connecting their accounts

In each tool's app settings, register the redirect URI `{APP_URL}/oauth/<google|slack|atlassian>/callback`.

| Variable | Where to get it |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | console.cloud.google.com → APIs & Services → Credentials → OAuth client ID (Web). Enable the Drive API and add test users on the consent screen. |
| `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` | api.slack.com/apps → your app → Basic Information. Add the User Token Scopes listed in `backend/README.md`. |
| `SLACK_TEAM_ID` | The `T…` part of `app.slack.com/client/T…/` in your browser |
| `ATLASSIAN_CLIENT_ID`, `ATLASSIAN_CLIENT_SECRET` | developer.atlassian.com/console → OAuth 2.0 (3LO). Enable the Jira, Confluence and User identity APIs. |
| `ATLASSIAN_CLOUD_ID` | `cloudId` at `https://<site>.atlassian.net/_edge/tenant_info` |

### Backend: admin credentials (background sync)

Check them with `docker compose run --rm --no-deps backend python -m app.connectors`.

| Variable | Where to get it |
|---|---|
| `ATLASSIAN_BASE_URL`, `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN` | Your site URL, plus a site admin's email and API token from id.atlassian.com → Security → API tokens |
| `SLACK_BOT_TOKEN` | `xoxb-…` from your app's OAuth & Permissions page (bot scopes: `docs/connectors/SLACK.md`) |
| `GOOGLE_REFRESH_TOKEN` | Personal Gmail: see `docs/connectors/GOOGLE_DRIVE.md` |
| `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_ADMIN_EMAIL` | Google Workspace, instead of `GOOGLE_REFRESH_TOKEN`: the service-account key JSON on one line, in single quotes, and an admin's email |

`LLM_*`, `AUDIT_LOG_SIGNING_KEY` and `TENCENTCLOUD_*` are not used yet.

## 3. Unit tests

```
cd backend
uv sync          # first time, and after every pull
uv run pytest    # all tests; one test: uv run pytest -k <name>
```

- Run them from `backend/`. Running from the repo root fails with `No module named 'app.connectors'`.
- No Docker or database needed: tests use a temporary SQLite file.
- Tests never call real external APIs; the tools are faked.
- Tests go in `backend/tests/`, named after the behaviour they check.

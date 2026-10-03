# DEVELOPMENT.md

Development guidelines. Stack: Next.js + FastAPI + PostgreSQL/pgvector,
run with Docker Compose (DECISIONS.md, ADR-001).

## 1. Local setup

1. Clone the repository.
2. Copy `backend/.env.example` to `backend/.env` and
   `frontend/.env.example` to `frontend/.env`, then fill in local values.
   `.env` files are git-ignored and must never be committed.
3. Install Docker Desktop (with Compose v2). Nothing else is needed to run
   the app; Node and Python are only needed for editing outside containers.
4. For backend work outside containers (tests, editor autocomplete), install
   [uv](https://docs.astral.sh/uv/getting-started/installation/) and run
   `uv sync` in `backend/`. It creates `backend/.venv` with Python 3.12 and
   every dependency; select that interpreter in your editor. Add a package
   with `uv add <pkg>` (or `uv add --dev <pkg>` for dev-only tools), which
   updates `pyproject.toml` and `uv.lock` together; commit both.
   No activation needed: `uv run <command>` (e.g. `uv run pytest`) uses
   `backend/.venv` automatically. To type plain `python` or `pytest` instead,
   activate it first: `source .venv/bin/activate` (macOS/Linux) or
   `.venv\Scripts\activate` (Windows).

## 2. Environment variables

All configuration and every secret come from the environment. Rules:

- Each app owns its config: `backend/.env.example` and
  `frontend/.env.example` list every variable that app reads, with a comment
  and a placeholder value. They are the documentation of configuration.
- Add a variable to its app's `.env.example` in the same change that
  introduces it.
- `docker-compose.yml` loads each app's `.env` and sets only container
  hostnames (`POSTGRES_HOST`, `BACKEND_URL`), which differ inside Docker.
- Never log a secret. Never put one in a prompt, fixture, screenshot or commit.
- Scripts and tests read credentials from the environment, never from
  arguments or hard-coded values.

## 3. Running the application

| Step | Command |
|---|---|
| First run, or after pulling changes | `docker compose up --build` |
| Start developing | `docker compose up` |
| After editing code | `docker compose up --build` (or one service: `docker compose up --build backend`) |
| Stop | Ctrl+C, or `docker compose stop` from another terminal |

- Code is copied into the images, so edits only take effect after `--build`.
  Docker's layer cache keeps rebuilds fast; dependencies are reinstalled only
  when `package.json` or `uv.lock` change.
- Stopping keeps containers, images and the database. `docker compose down`
  also removes containers; `docker compose down -v` also wipes the database.
- Frontend: http://localhost:3000 (shows the backend health result)
- Backend: http://localhost:8000/health returns `{"db": "ok", "pgvector": "<version>"}`
- Postgres is reachable only inside the Compose network.
- Schema changes are Alembic migrations in `backend/migrations/versions/`. The
  `migrate` service applies them before the backend starts; deployments run the
  same `alembic upgrade head` against TencentDB. New migration: add the next
  numbered file there, with `down_revision` set to the previous `revision`.
- The images are production images (non-root, health checks); local runs use
  exactly what gets deployed.

A mocked-connector demo mode will be added with the first connector. Mocked
mode must be visibly labelled in the UI or output.

## 4. Running tests

Backend: pytest in `backend/tests/`. From `backend/`: `uv run pytest`.
Expectations:

- One command runs the whole suite.
- Security-invariant tests (SECURITY.md section 2) are tagged so they can be
  run on their own and are always part of the default run.
- Tests never call real external APIs without an explicit opt-in flag.

## 5. Linting and formatting

`TBD` (still open in ADR-001). Whatever is chosen, it runs in one command and in CI, and the
repository stays clean under it. Do not argue about style in PRs; let the tool
decide.

## 6. Git workflow

- `main` is always in a demoable state. Nothing is committed directly to
  `main` after the initial scaffold.
- Work happens on short-lived branches merged through pull requests.
- Rebase or merge from `main` before opening a PR; resolve conflicts locally.
- Never force-push `main`. Never rewrite shared history.
- Never commit generated output, local databases or secrets (see `.gitignore`).

### Branch naming

`<type>/<short-kebab-description>` where `type` is one of
`feat`, `fix`, `docs`, `test`, `chore`, `spike`.

Examples: `feat/audit-hash-chain`, `docs/adr-003-authz-model`,
`spike/confluence-permissions-api`.

### Commit conventions

[Conventional Commits](https://www.conventionalcommits.org/) style:

```
<type>(<scope>): <imperative summary, 72 chars max>

<optional body: what and why, not how>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `security`.
Use `security` for any change to authorization, filtering, audit logging, or
what the LLM receives, so the history is searchable.

### Pull requests

Every PR description states:

1. What changed and why (link the ADR or scenario it serves).
2. **Security impact:** "none" or a description. Changes to security behaviour
   need review from a second team member and must never be merged silently.
3. New dependencies, each with a one-line justification.
4. Documentation updated: yes / not needed (say which files).
5. Tests added or updated.
6. Whether any part is mocked, and where that is labelled.

Small PRs. One concern each. Reviewers check the security-impact line first.

## 7. How to add an integration (source connector)

1. Read the platform's native permission model and write it down in
   [ARCHITECTURE.md](architecture/ARCHITECTURE.md) before writing code. Confluence,
   Jira, Slack and Google Drive each differ; the handbook forbids flattening.
2. Decide, and record in the PR, whether the connector is **real** or
   **mocked**. A mock must be named as such in code, be visibly labelled in
   any output, and model realistic permission structures so the negative
   cases can be demonstrated.
3. The connector exposes content *and* permission data. It never makes an
   authorization decision itself; that is the authorization layer's job.
4. Use least-privilege credentials, configured only via environment variables
   listed in `backend/.env.example`.
5. Add tests: content fetch, permission fetch, and at least one negative
   permission case for this platform.
6. Add the audit events the connector's actions produce.
7. Update ARCHITECTURE.md (section 3.6) and, if the design changed, an ADR.

## 8. How to add tests

- Backend tests go under `backend/tests/`, mirroring `backend/app/`; frontend
  tests live in `frontend/`.
- Name tests after the behaviour, not the function:
  `revoked_channel_membership_excludes_messages`, not `test_filter_2`.
- Every security invariant in SECURITY.md gets at least one test that would
  fail if the invariant were broken. Link the test from the SECURITY.md table.
- Negative cases are first-class: for every "user X can see Y" test, write the
  matching "user Z cannot see Y, and the response does not reveal Y exists".
- Tests for permission changes must exercise the change *after* ingestion.
- Prefer small deterministic fixtures with clearly fake data (obviously fake
  names, no real company data).

## 9. How to update documentation

- Documentation is part of the change, not a follow-up. A PR that changes
  architecture or important behaviour updates the relevant doc in the same PR.
- Root documents and their purpose:
  - `README.md` – entry point and current status
  - `PROJECT.md` – what and why, personas, scenarios, MVP scope, open items
  - `ARCHITECTURE.md` – shape of the system and open questions
  - `SECURITY.md` – threat model and invariants
  - `DECISIONS.md` – decision log; full ADRs under `docs/decisions/`
  - `DEVELOPMENT.md` – this file
  - `AGENTS.md` – instructions for AI coding agents
  - `docs/hackathon/` – challenge, requirements, submission, tool-usage
- Mark anything undecided as `TBD` and anything assumed as `ASSUMPTION:` so
  it can be found with a search. Remove the marker when it is resolved.
- When a TBD is resolved, update the "Open items" table in PROJECT.md.
- Use the ADR template in `docs/decisions/adr-template.md` for decisions.

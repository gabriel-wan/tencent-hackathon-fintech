# Contributing to KnowBuddy

**For:** the team (and AI agents working with us).
**You'll:** ship a change the way we do: branch, commit, pull request, review, merge, and record decisions.
**Not here:** running the app → [docs/RUNNING.md](docs/RUNNING.md) · testing → [docs/TESTING.md](docs/TESTING.md) · security rules → [docs/SECURITY.md](docs/SECURITY.md) · agent-specific rules → [AGENTS.md](AGENTS.md).

## The short version

1. Branch from `main` as `<type>/<what-it-does>`.
2. Commit with Conventional Commits: `feat(audit): add the verify route`.
3. Open a pull request and fill in **all six sections** of the template.
4. Anything under "Security changes" needs a **second teammate's approval**.
5. Merge with **Create a merge commit**, never squash.
6. Update the docs **in the same PR** as the behaviour they describe; §9 says which page.

## 1. Branches

- `main` is always demoable. Nothing is committed to it directly; every change arrives through a pull request.
- Name a branch `<type>/<short-kebab-description>`, using the commit types below. Examples from this repo:
  `feat/task3-audit-log`, `fix/ui-accessibility-and-responsive`, `docs/pr-template`, `chore/knowbuddy-rename-docs`.
- Keep branches short-lived. To catch up with `main`, **merge** it into your branch (`git merge origin/main`).
  Never rebase a branch you've pushed: teammates may have pulled it.
- A branch can be built on another one (stacked). Merge the lower one first.
- Never force-push `main`. Never commit `.env` files, secrets, local databases or generated output.

## 2. Commits

```
<type>(<scope>): <imperative summary, at most 72 characters>

<body: what changed and why, not how>
```

| Type | For |
|---|---|
| `feat` | Something new a user or teammate can use |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `test` | Tests only |
| `refactor` | Same behaviour, different code |
| `chore` | Tooling, dependencies, renames |
| `security` | Any change to authorization, filtering, audit logging or what the LLM receives, so these are easy to find in the history |

The scope is the area: `frontend`, `audit`, `connectors`, `sync`, `query`, `db`… One concern per commit.

## 3. Pull requests

Every PR uses the template in [.github/pull_request_template.md](.github/pull_request_template.md). GitHub fills it
in when you open a PR on the website; if you (or an agent) open one any other way, copy the sections yourself.
Keep all six, in order, and write "None" in a section that doesn't apply.

| Section | Write |
|---|---|
| Summary | What changed, which files, and why. Link the ADR, scenario or issue it serves |
| New Features | What a user or teammate can now do, briefly, and how it works. Name any new dependency with a one-line reason |
| Setup changes for teammates | New `.env` variables, migrations or commands. Teammates read this first after pulling |
| Security changes | Anything touching authorization, filtering, audit logging or what the LLM receives. Not "None" → needs a second reviewer (section 4) |
| How it was tested | The commands you actually ran and their results (e.g. "pytest: 203 passed"), and what you checked by hand |
| Checklist | Docs updated; no secrets in code, commits or screenshots |

Keep PRs small, with one concern each. If something is mocked, say where it's labelled as mocked (AGENTS.md §2.5).

## 4. Reviews

- Every PR is reviewed by a teammate before it merges. Reviewers read **Security changes** first.
- A PR whose Security changes isn't "None" needs a **second teammate's approval**. It is never merged silently.
- Review on GitHub with **Review changes** → Approve, Request changes or Comment. Say what you checked
  (tests run, files read), so the next reviewer doesn't repeat it.
- If you push to someone else's branch (for example, to resolve a conflict with `main`), say so in a PR comment.

## 5. Merging

- Use **Create a merge commit**. Not "Squash and merge" or "Rebase and merge": they rewrite the branch's
  commits, which breaks any branch built on top of it.
- After merging, delete the branch on GitHub, then update your local `main` (`git checkout main` and `git pull`).

## 6. Issues

- One issue per problem, with a GitHub label: `bug`, `enhancement`, `documentation`, `question`,
  `accessibility` or `security`.
- **Security problems:** tell the team in the team channel straight away, and open an issue labelled `security`.
  Don't push a fix that changes security behaviour without a second teammate's review ([SECURITY.md](docs/SECURITY.md) §5).

## 7. How we decide

The decision log is [docs/decisions/DECISIONS.md](docs/decisions/DECISIONS.md). Each entry is an ADR (architecture
decision record).

**What needs an ADR:** the tech stack, any security behaviour, the data model, an external service, and anything a
judge might ask "why did you do it this way?" about. Naming, styling and refactors don't.

**How a decision is made:**
1. **Propose** it in the team chat, a meeting or a pull request, with the options and their trade-offs.
2. **Discuss** it with the people it affects. Cross-cutting decisions go to a team meeting (ADR-002 to ADR-008 were
   decided together on 3 Oct). A decision inside one area can be made by that area's owner (below) and recorded in
   their PR.
3. **Record** it in DECISIONS.md as **Accepted**, with the date and who decided, using
   [adr-template.md](docs/decisions/adr-template.md). An ADR is only Accepted once the team has actually discussed it.
4. **Change** it later with a dated amendment, never by rewriting it: either a short `*Amended YYYY-MM-DD:*` note, or
   an "Amendment" section with **Was / Now / Why / Cost** (see ADR-001 and ADR-002).
5. **Replace** it with a new ADR marked "Supersedes ADR-NNN". Old ADRs are kept, not deleted.

**Who owns what:**

| Area | Owner |
|---|---|
| Connectors, sync, companies (roadmap Task 1) | Vincent |
| Frontend (roadmap Task 2) | Zewei |
| Query pipeline and audit log (roadmap Task 3) | Gabriel |

**Open questions:** mark anything undecided `TBD` and anything assumed `ASSUMPTION:` in docs and code comments, so a
search finds them. A question that needs an answer becomes a GitHub issue (label `question`); if the answer is a
decision of the kind above, it becomes an ADR. Never settle a `TBD` in code without one.

## 8. Making changes

**Backend dependencies (uv).** Declared in `backend/pyproject.toml`, with exact versions locked in `backend/uv.lock`.
Run these from `backend/`.

| Task | Command |
|---|---|
| Set up, and again after every pull | `uv sync`. It creates `backend/.venv` with Python 3.12 and dev tools such as pytest. Select `.venv` as your editor's interpreter |
| Run anything | `uv run <cmd>`, e.g. `uv run pytest`. No activation needed |
| Add a package | `uv add <pkg>`, or `uv add --dev <pkg>` for test-only tools |
| Remove a package | `uv remove <pkg>` |
| Upgrade a package | `uv lock --upgrade-package <pkg>`, then `uv sync` |

- Always commit `pyproject.toml` and `uv.lock` together. Never use `pip install`.
- The Docker image installs exactly what `uv.lock` lists (`uv sync --locked --no-dev`). If you edit
  `pyproject.toml` by hand, run `uv lock` before building, or the build fails.

**Frontend dependencies (npm).** From `frontend/`: `npm install <pkg>` updates `package.json` and
`package-lock.json`; commit both. Adding a shadcn component: [frontend/README.md](frontend/README.md).

**Database changes.**
- Write a numbered migration in `backend/migrations/versions/`, with `down_revision` set to the previous one.
  If two branches add the same number, whoever merges second renumbers theirs. If your local database ran a
  migration that was later renumbered, reset it with `docker compose down -v` (this wipes your local data).
- Migrations run as the database owner; the app logs in as `knowbuddy_app` (`app/db.py`, password
  `APP_DB_PASSWORD`). New tables get the app's usual rights automatically, but not TRUNCATE: tests that empty
  tables use `owner_engine()`.
- `audit_events` is read-and-add only for the app. Never write code that updates or deletes audit records, and make
  `record_event` the last statement of a short transaction: it holds the company's chain lock until commit.

**Tests.**
- Backend tests go in `backend/tests/`, frontend tests next to the code they test (`*.test.ts`).
- Name a test after the behaviour it checks: `revoked_channel_membership_excludes_messages`, not `test_filter_2`.
- Every security invariant in SECURITY.md has at least one test that would fail if the invariant broke; link it
  from SECURITY.md's table. For every "X can see Y" test, write the matching "Z can't see Y, and nothing reveals
  that Y exists".
- Use clearly fake data. Tests never call real external APIs: the LLM and the tools are faked.

**A new connector.** Read the tool's own permission model first and preserve it (never flatten it). The connector
fetches content and permissions but never decides who may see what: that's the authorization layer's job. Add
tests for fetching, for permissions, and at least one negative permission case, and add the audit events its
actions produce. How connectors plug in: [docs/architecture/CONNECTORS.md](docs/architecture/CONNECTORS.md).

**Scripts** (`scripts/`). Read credentials only from the environment, never from arguments or code. Anything
that seeds or resets data must say so in its name and refuse to run against anything but a local database.

## 9. Docs

Docs are part of the change: a pull request that changes behaviour, setup or architecture updates the matching doc in
the same pull request. Stale docs are bugs; if you find one, fix it or open a `documentation` issue.

**When you change something, update its one home.** Each topic is written in one place, and other pages link to it.
The full map is [docs/README.md](docs/README.md).

| When you change… | Update… |
|---|---|
| A setting (`.env` variable) | `backend/.env.example` or `frontend/.env.example`, and [RUNNING.md](docs/RUNNING.md)'s appendix. If everyone must set it, also RUNNING.md §2 and the PR's "Setup changes" |
| An API route or its response | [QUERY_PIPELINE.md](docs/architecture/QUERY_PIPELINE.md) §2 (the app's API) or [CONNECTORS.md](docs/architecture/CONNECTORS.md) §3 (sign-in and admin routes). Then regenerate the frontend's types: `npm run gen:api-types` |
| The database (a migration) | [ARCHITECTURE.md](docs/ARCHITECTURE.md) §7 (the data-model diagram and its table) |
| A container, a backend module, or what talks to what | [ARCHITECTURE.md](docs/ARCHITECTURE.md) §3 and, for a module, [backend/README.md](backend/README.md) |
| Who may see what (authorization, filtering, audit, what the LLM receives) | [SECURITY.md](docs/SECURITY.md) §2, with a link to the test that guards it; an ADR if the design changed (§7 above) |
| A decision | [DECISIONS.md](docs/decisions/DECISIONS.md): a new ADR or a dated amendment (§7 above) |
| A page or how the website behaves | [architecture/FRONTEND.md](docs/architecture/FRONTEND.md); for commands or styling rules, [frontend/README.md](frontend/README.md) |
| How a connector signs in, syncs or checks access | [architecture/CONNECTORS.md](docs/architecture/CONNECTORS.md); a tool's sign-in set-up steps, [connectors/SETUP.md](docs/connectors/SETUP.md) |
| What a user sees in one of the five scenarios | [FEATURES.md](docs/FEATURES.md): re-run its "Try it" and update "You'll see" with the real output |
| How to run it, or a problem you hit and solved | [RUNNING.md](docs/RUNNING.md); a new problem gets a row in §8, "When something goes wrong" |
| A test file, a test command or a manual check | [TESTING.md](docs/TESTING.md) |
| Deploying | [DEPLOYMENT.md](docs/DEPLOYMENT.md), with what was actually done |
| A task's progress, or a new open question | [PROJECT.md](docs/PROJECT.md): the roadmap's status column, or "Open items" |
| A new doc page | Add it to [docs/README.md](docs/README.md)'s map; if it is one of the main guides, to the README's table too |

**How a page is written:**
- Every guide opens with three lines: **For:** who it's for, **You'll:** what they'll get, **Not here:** where to go
  instead. Copy them from any existing guide.
- Write about what is built. Planned work goes in [PROJECT.md](docs/PROJECT.md), clearly labelled; never describe
  something planned as if it works. Mark guesses `ASSUMPTION:` and undecided items `TBD`.
- A how-to step ends with how you know it worked: "✅ …".
- Plain language, short sentences. Name the file or command a reader needs (`app/sync.py`, `docker compose logs sync`).
- Link to a topic's one home rather than repeating it. When you move or rename a section, update every link to it.

**Diagrams** are Mermaid, so GitHub draws them and they show up in diffs:
- In flowcharts, don't put boxes inside group boxes (`subgraph`): GitHub draws arrows straight through the group's
  title. Colour boxes by role with `classDef` instead, as ARCHITECTURE.md §2 does.
- In sequence diagrams, never use a semicolon in a message: it ends the line and breaks the diagram.
- Add `%%{init: {"flowchart": {"wrappingWidth": 360}}}%%` as a flowchart's first line, so labels aren't wrapped
  mid-phrase.
- Check it renders before you commit: paste it into https://mermaid.live, or look at the file on GitHub on your
  pushed branch.

**Before opening a pull request that touches docs,** check every link still works:

```bash
python3 scripts/check_doc_links.py
```

## 10. Hackathon evidence

The hackathon only scores projects that prove they were built with CodeBuddy or WorkBuddy.

- Use CodeBuddy or WorkBuddy for real work, and take screenshots **as you go**. Never stage or fabricate them later.
- Save them in [docs/hackathon/evidence/](docs/hackathon/evidence/) as `YYYY-MM-DD-<tool>-<topic>.png`, and add a
  row to the log in [docs/hackathon/tool-usage.md](docs/hackathon/tool-usage.md).
- Crop or blur any secret, token or personal data before committing.

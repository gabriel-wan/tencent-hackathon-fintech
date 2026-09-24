# DEVELOPMENT.md

Development guidelines. The technology stack is **not yet chosen**
(DECISIONS.md, ADR-001), so setup, run, test and lint instructions below are
framework-agnostic placeholders. **Update this file in the same PR that
introduces the stack.**

## 1. Local setup

1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in local values. `.env` is
   git-ignored and must never be committed.
3. Install the toolchain and dependencies: `TBD (ADR-001)`.
4. Run the checks in section 4 to confirm the environment works.

## 2. Environment variables

All configuration and every secret come from the environment. Rules:

- `.env.example` lists every variable the application reads, with a comment
  and a placeholder value. It is the documentation of configuration.
- Add a variable to `.env.example` in the same change that introduces it.
- Never log a secret. Never put one in a prompt, fixture, screenshot or commit.
- Scripts and tests read credentials from the environment, never from
  arguments or hard-coded values.

## 3. Running the application

`TBD (ADR-001)`. When defined, this section will contain one command to run
the application locally and one to run it with mocked connectors for demos.
Mocked mode must be visibly labelled in the UI or output.

## 4. Running tests

`TBD (ADR-001)`. Expectations regardless of framework:

- One command runs the whole suite.
- Security-invariant tests (SECURITY.md section 2) are tagged so they can be
  run on their own and are always part of the default run.
- Tests never call real external APIs without an explicit opt-in flag.

## 5. Linting and formatting

`TBD (ADR-001)`. Whatever is chosen, it runs in one command and in CI, and the
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
   `docs/architecture/permission-model.md` before writing code. Confluence,
   Jira, Slack and Google Drive each differ; the handbook forbids flattening.
2. Decide, and record in the PR, whether the connector is **real** or
   **mocked**. A mock must be named as such in code, be visibly labelled in
   any output, and model realistic permission structures so the negative
   cases can be demonstrated.
3. The connector exposes content *and* permission data. It never makes an
   authorization decision itself; that is the authorization layer's job.
4. Use least-privilege credentials, configured only via environment variables
   listed in `.env.example`.
5. Add tests: content fetch, permission fetch, and at least one negative
   permission case for this platform.
6. Add the audit events the connector's actions produce.
7. Update ARCHITECTURE.md (section 3.6) and, if the design changed, an ADR.

## 8. How to add tests

- Put tests under `tests/`, mirroring the structure of `src/`.
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

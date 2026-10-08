# DECISIONS.md – architecture decision log

Short record of every significant decision. Longer ADRs go in this folder
using [adr-template.md](adr-template.md) and are linked from here.

Rules: a decision is only "Accepted" once the team has actually discussed it.
Placeholders stay "Proposed" with empty content; do not fill them in
speculatively. Superseded decisions are kept, not deleted.

| ADR | Title | Status |
|---|---|---|
| [000](#adr-000-repository-initialization) | Repository initialization | Accepted |
| [001](#adr-001-technology-stack) | Technology stack | Accepted |
| [002](#adr-002-authentication-and-identity-model) | Authentication and identity model | Accepted |
| [003](#adr-003-authorization-model) | Authorization model | Accepted |
| [004](#adr-004-retrieval-architecture) | Retrieval architecture | Accepted |
| [005](#adr-005-dataindexing-architecture) | Data / indexing architecture | Accepted |
| [006](#adr-006-llmprovider-selection) | LLM / provider selection | Accepted |
| [007](#adr-007-audit-log-design) | Audit-log design | Accepted |
| [008](#adr-008-deployment-architecture) | Deployment architecture | Accepted |

---

## ADR-000: Repository initialization

- **Status:** Accepted
- **Date:** 2026-09-24
- **Deciders:** Team (repository set up on the team's instruction)

### Context

The team of three has about three weeks until the 16 Oct 2026 submission for
the Aspire "Internal Brain" challenge. The challenge is unusual in that its
hardest requirements are security properties (permission-aware retrieval,
no leakage in negative cases, live permission changes, tamper-evident audit)
rather than features. Those properties are very hard to retrofit. The team
also has to prove CodeBuddy/WorkBuddy usage and deliver an architecture and
trust-boundary diagram, both of which benefit from a shared written record.

### Decision

Create a structured repository with documentation **before** any
implementation:

- Root documents for project scope, architecture questions, security threat
  model and invariants, development conventions, this decision log, and agent
  instructions.
- Organised extracts of the hackathon handbook so the team does not rely on
  memory of the requirements.
- A submission checklist and a tool-usage evidence log.
- Empty `src/`, `tests/`, `scripts/` with short READMEs stating what belongs
  there and that nothing goes in until ADR-001.
- No technology, framework, database, LLM or cloud service chosen.

### Consequences

- The team has one shared source of truth for requirements, decisions and
  security rules, readable by humans and AI coding agents alike.
- Implementation is deliberately delayed until the team has reviewed
  ARCHITECTURE.md and made ADR-001. This costs a little time now and is
  expected to save more later.
- Documentation must be kept current; stale docs are treated as bugs
  (AGENTS.md §3).

### Assumptions

- `ASSUMPTION:` The handbook PDF in `docs/hackathon/handbook.pdf` is the
  current official version. Verify against the version emailed to the team.
- `ASSUMPTION:` The "Solution Should Be" list under the FinTech track in the
  handbook is a copy error from the Healthcare track and is not a requirement.

---

## ADR-001: Technology stack

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** v1-nce
- **Scope:** language, web/API framework, test runner, linter/formatter,
  package manager. Also whether any Tencent Cloud service is part of the
  stack.
- **Must consider:** what all three members can work in productively for
  three weeks; what CodeBuddy/WorkBuddy support well; what is easiest to demo.

### Decision

- Frontend: Next.js (TypeScript, App Router, npm) in `frontend/`.
- Backend: FastAPI (Python 3.12, uv) in `backend/`; tests with pytest in
  `backend/tests/`. Dependencies in `backend/pyproject.toml` (dev tools in the
  `dev` dependency group), pinned by `backend/uv.lock`.
- Database: PostgreSQL 17 with the pgvector extension, so documents,
  permissions, embeddings and the audit log live in one database.
- Local run: Docker Compose (`db`, `backend` on :8000, `frontend` on :3000).
- Schema: Alembic migrations, applied by the same command locally and on deploy.
- Linter/formatter: still open. Tencent Cloud services and the LLM are decided
  in ADR-005, ADR-006 and ADR-008.

### Consequences

- Two runtimes (Node, Python), kept apart by folder; no monorepo tooling.
- One `docker compose up` runs everything; the database is not exposed to
  the host.

### Amendment (2026-10-03): pip → uv

- **Was:** pip with `backend/requirements.txt`.
- **Now:** uv with `backend/pyproject.toml` + `uv.lock`.
- **Why:** dependency groups (PEP 735) keep dev tools such as pytest out of
  the production image, and pip cannot install a project's dependencies
  without packaging the app. uv also locks every transitive dependency.
- **Cost:** each developer installs uv once (`docs/RUNNING.md` §1).

## ADR-002: Authentication and identity model

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Vincent, Zewei, Gabriel (team meeting)
- **Scope:** how a user is authenticated in the prototype; how one principal
  maps to Confluence, Jira, Slack and Google Drive identities; where group
  membership is resolved. Relates to SECURITY.md INV-3.

### Decision

- **No separate app login.** Identity comes from the connectors, the way
  connectors work in Claude: a user adds a connector and signs in to it with
  their company account (Google for Drive, Slack for Slack). The verified
  account from that sign-in is who the user is.
- **The administrator sets up the company's sources** (the company Drive and
  Slack workspace, later Jira and Confluence) and defines the **boundary**:
  which Slack channels and Drive folders the system may use.
- A user can only access content that is **inside the administrator's
  boundary and** that the user may read in the source platform. Content
  outside the boundary is never used, even if the user can see it in the
  source platform.

### Consequences

- Identity is verified by the platform's own sign-in, then held in a
  server-side session. The browser never sends a user ID that the backend
  trusts (INV-3).
- One person's Slack and Google identities are linked by their company email
  address.
- Effective access is the intersection of two checks: the admin boundary and
  the user's source-platform permission. Both are enforced in code before
  anything reaches the LLM (ADR-003).
- Only content inside the boundary is ingested, so nothing outside it is
  indexed or sent to the embedding model (ADR-005).
- Changing the boundary is a security-relevant admin action and is recorded
  in the audit log (ADR-007).

### Amendment (2026-10-05): many companies per deployment

- **Was:** one company per deployment, set by environment variables
  (`SLACK_TEAM_ID`, `ATLASSIAN_CLOUD_ID`, `GOOGLE_ALLOWED_ACCOUNTS`), with sync
  reading through company-wide admin credentials (Slack bot, Google service
  account, Atlassian API token).
- **Now:** a `companies` table; every document, boundary scope and sync cursor
  belongs to one company, and so does every user once a connection names it. The first full member (not a guest) to sign in
  from a new Slack workspace creates its company and becomes the admin; later
  sign-ins from it join. *Amended 2026-10-07:* Atlassian sign-ins never create
  a company and never become admin, since Atlassian can't tell a contractor
  from an employee; the admin adds the company's site by connecting Jira. Google names no company, so tools connect in any
  order: a user with only Google has no company and sees nothing. Sync reads as the admin's own connections; live checks ask
  each source as the asking user.
- **Why:** the product should serve any number of companies from one
  deployment. Principals held in every company (`public`, `slack:members`) made
  a company filter in search necessary, not optional.
- **Cost:** sync sees only what the company admin can see. Whoever controls a
  Slack workspace or Atlassian site can start a company from it (no approval step yet). Serving other
  companies in production needs Google's verification for Drive, Atlassian's
  Personal Data Reporting API, and Slack Marketplace approval (rate limits).

---

## ADR-003: Authorization model

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Vincent, Zewei, Gabriel (team meeting)
- **Scope:** where authorization is evaluated; how per-platform permission
  semantics are represented without flattening; how permission changes after
  ingestion are handled; deny-by-default. Relates to INV-1, INV-2, INV-4,
  INV-5, INV-8.

### Decision

Before anything is sent to the LLM, permissions are **re-checked against the
source platform**. The stored permission data filters search results; the
live check against the source has the final say.

Data flow and per-source check calls are described in
[CONNECTORS_ARCHITECTURE.md](../architecture/CONNECTORS_ARCHITECTURE.md).

### Consequences

- A revoked permission takes effect on the very next question, not at the
  next sync. This directly covers challenge scenario 4.
- Each connector provides a "can this user still read this item?" check.
- Deny by default: a "no", an error, a timeout or a deleted item drops the
  item. A source outage therefore produces a less complete answer, never a
  leak.
- Live checks add latency to every question, so the number of items checked
  is capped and the checks run in parallel.

---

## ADR-004: Retrieval architecture

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Vincent, Zewei, Gabriel (team meeting)
- **Scope:** live API vs index vs hybrid; cross-platform fan-out and ranking;
  which connectors are real and which are mocked; behaviour when a source is
  unavailable.

### Decision

- Start with **Slack and Google Drive**, using their **real APIs** against
  the team's own test Slack workspace and Google account, filled with
  fictional fintech seed data.
- Add **Jira and Confluence** later.
- Connector details per platform are in [docs/connectors/](../connectors/).

### Consequences

- No mocks are needed for the first two sources, so the demo shows real
  platform permissions.
- All seed data in the test workspace and Drive is fictional. No real people,
  customers or company data.
- Slack guest accounts need a paid plan, and a new Google OAuth app in testing
  mode issues tokens that expire after 7 days. The demo personas and setup
  must work within those limits.

---

## ADR-005: Data / indexing architecture

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Vincent, Zewei, Gabriel (team meeting)
- **Scope:** what is stored, how content is chunked/indexed, whether
  embeddings and a vector store are needed for the MVP, how permission
  metadata travels with indexed content, the freshness window and how it is
  achieved. Relates to INV-8 (stale permissions) and the data-freshness scenario.

### Decision

- **Hybrid search:** keyword (Postgres full-text) plus semantic (pgvector)
  search, merged by rank.
- **Embedding model:** `kinfra-text-embedding-0.6b` on Tencent Cloud TokenHub,
  1,024 dimensions.
- **Change detection by polling, no webhooks:** sync every 5 minutes, plus a
  slower sweep for deletions and permission changes, as described in
  [CONNECTORS_ARCHITECTURE.md](../architecture/CONNECTORS_ARCHITECTURE.md).
- **An administrator "sync now" action** triggers an immediate sync, for the
  live freshness demo.

### Consequences

- The stated freshness window for new or edited content is about 5 minutes
  plus processing time, inside the handbook's "minutes to about 1 hour".
- Permission revocations do not wait for the sync: the live check (ADR-003)
  applies them on the next question.
- *Amended 2026-10-07 (Task 1):* the sweep is not built yet; instead every
  sync reads each boundary scope in full, which refreshes all ACLs and catches
  deletions. Syncs of one company never overlap (advisory lock), and a scope
  removed mid-sync is not written back. Stale content is labelled, not hidden:
  each citation carries `synced_at` (the scope's last complete sync). A deleted
  Slack message drops at the next sync, since Slack's live check is per
  channel; Drive, Jira and Confluence deletions (Drive trash included) drop at
  the live check.
- 1,024-dimension vectors fit pgvector's standard index. The larger 4b model
  (2,560 dimensions) would not, without extra work.
- The embedding model receives the text of every in-boundary document at
  ingestion. TokenHub states data is not used for training and stays in the
  Singapore region.
- Webhooks would need a public HTTPS endpoint and signature checks. They are
  not used.

---

## ADR-006: LLM / provider selection

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Vincent, Zewei, Gabriel (team meeting)
- **Scope:** provider and model; grounding and citation strategy;
  hallucination mitigation; what the model never sees. Relates to INV-1,
  INV-2, INV-9.

### Decision

- **Model:** Tencent Hunyuan `hy3`, through Tencent Cloud TokenHub in the
  Singapore region (OpenAI-compatible API). Default thinking setting for now.
- **Grounding rules:**
  - Every claim cites a source ID.
  - When the sources do not answer the question, the model replies with a
    fixed "not found" sentence.
  - When no source passes the permission check, the LLM is not called; the
    same fixed sentence is returned.
  - Any citation outside the allowed set is rejected by our code.
  - Retrieved content is wrapped as untrusted data, never instructions.

### Consequences

- Evidence: on 2026-10-03, `hy3` passed 18 of 18 runs of a grounding smoke
  test (answerable question, unanswerable question, prompt injection inside a
  retrieved message), with thinking on and turned down. Average latency was
  about 6 to 7 seconds per answer.
- The thinking setting can be lowered later to cut latency and cost; the
  smoke test showed no quality loss with `reasoning_effort=low`.
- *Amended 2026-10-07:* thinking is now **disabled** (`thinking: disabled`).
  Measured: hidden reasoning was ~90% of each reply's tokens; answers took
  ~7 s with thinking on, ~2 to 4 s off (`reasoning_effort=low` barely helped).
  The same three-case smoke test passed 9 of 9 with thinking off. Replies are
  capped at 1,024 tokens, safe because no reasoning tokens count against it.
- Skipping the LLM when nothing is allowed gives the same reply whether
  nothing exists or nothing is permitted (scenario 3, INV-5).
- TokenHub states API data is not used for training, and data stays in the
  Singapore region.
- Calls go through one small interface, so another OpenAI-compatible model can
  be swapped in by changing configuration.
- Every team member who calls the API needs the key in their local
  `backend/.env`. The account needs a positive balance, and pay-as-you-go must
  be enabled before the demo so the free quota cannot run out mid-demo.

---

## ADR-007: Audit-log design

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Vincent, Zewei, Gabriel (team meeting)
- **Scope:** event schema (who / what / when / decision / answer); tamper-
  evidence mechanism; storage; query interface for the compliance persona;
  access control on the log itself. Relates to INV-6, INV-7.

### Decision

- **One role:** the administrator and compliance officer are merged. The
  same role manages the boundary (ADR-002) and queries the audit trail.
- **Storage and tamper-evidence:** an append-only table in Postgres. Each
  record stores the hash of the previous record, forming a hash chain. The
  application's database role can insert into this table but cannot update
  or delete. A **verify** action recomputes the chain and reports the first
  broken record, if any.
- **Fields in every record:**

  | Group | Fields |
  |---|---|
  | Who and when | Timestamp, user, role |
  | Request | Event type, question |
  | Decisions | Candidate document IDs, allow or deny for each with the reason, document IDs sent to the LLM |
  | Response | Answer, citations, model |
  | Chain | Previous hash, own hash |

- **Also logged:** boundary changes, connector setup, "sync now", and every
  search of the audit log itself.
- **Attempted access** (added 2026-10-04, Gabriel): each query record also
  lists the restricted documents the question matched, with the reason the
  user could not see them (not in the document's ACL, or outside the admin
  boundary). A separate audit-only search produces this list; its results
  never reach the user or the LLM. Only keyword matches count, because
  semantic search always returns the nearest documents, relevant or not, and
  would wrongly record users as reaching unrelated restricted documents.
- **One chain per company** (added 2026-10-08, Gabriel): companies (ADR-002
  addendum, migration 0005) came after this ADR. Each record now carries its
  user's company, and links to the previous record of the same company, so an
  admin verifies only their own company's records and a fault in one company
  never shows up in another. Records of people not yet in a company (e.g.
  Drive connected first) form their own chain. The hash is computed by a
  database function (`audit_event_hash`, migration 0006) over the record's id,
  UTC time, company, user, event type and canonical JSON payload, so writing
  and verifying always hash the same text. Writes to one chain are serialised
  with an advisory lock, so two records can never share a predecessor.
- **The app's database login** (added 2026-10-08, Gabriel; corrected the same
  day after review of PR #11 by Vincent and Zewei): migrations run as the
  database owner; the app logs in as `knowbuddy_app` itself, with its own
  password (`APP_DB_PASSWORD`, set on the database by the `migrate` service on
  every start). It can read and add audit records but not update, delete or
  truncate them, empty any table, or alter a table to switch the triggers off.
  The first version logged in as the owner and switched role on connect, and
  `SET ROLE NONE` switched back to the owner, a superuser in Docker; with its
  own login there is nothing more powerful to return to (tested). The owner's
  password is only needed by migrations and tests; a production server can
  leave it out of the backend's environment.
- **The chain lock** (added 2026-10-08, review of PR #11): `record_event` holds
  its company's lock until the caller's transaction ends, so it is the last
  statement of a short transaction (every caller today). Lock keys are 32-bit,
  so company ids are folded in; two companies sharing a key only wait for each
  other.
- **Records from before someone joined a company** (added 2026-10-08, review of
  PR #11): they stay in the no-company chain (the log can't be rewritten), and
  the company's admin can search them once the person has joined. Only the
  no-company chain as a whole can verify them, and no admin API does.
- **Search and verify** (added 2026-10-08, Gabriel): `GET /api/admin/audit`
  filters by user, time range, event type, document, and tool plus scope (the
  challenge's "everything jdoe accessed in the payment-gateway space");
  `POST /api/admin/audit/verify` reports the first broken record and the
  chain's head. The head can be noted outside the system, because someone with
  full database access could otherwise rewrite every later record. Results
  show document keys only; whether to show restricted documents' titles is
  still open (frontend/README.md, Open questions).

### Consequences

- One fewer persona to build and demo.
- The role that sets the boundary also reviews access, so there is no
  separation of duties. Because admin actions are themselves in the chain,
  they cannot be hidden from a later reviewer.
- The audit log contains questions and answers, so only the administrator
  role can read it.

---

## ADR-008: Deployment architecture

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Vincent, Zewei, Gabriel (team meeting)
- **Scope:** local-only vs hosted demo; whether a live link is submitted
  (optional, bonus points); which Tencent Cloud services, if any, are used;
  secrets handling in deployment.

### Decision

Host live on **one Tencent Cloud Lighthouse server** in Singapore, running
the existing Docker Compose setup, with the database on the same server.

### Consequences

- The submission includes a live link, which the handbook says earns bonus
  points.
- Local and live environments run the same containers.
- Secrets on the server come from environment variables, never from the
  repository.
- The live site must not expose real credentials or real company data.

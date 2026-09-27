# DECISIONS.md – architecture decision log

Short record of every significant decision. Longer ADRs go in
[docs/decisions/](docs/decisions/) using
[adr-template.md](docs/decisions/adr-template.md) and are linked from here.

Rules: a decision is only "Accepted" once the team has actually discussed it.
Placeholders stay "Proposed" with empty content; do not fill them in
speculatively. Superseded decisions are kept, not deleted.

| ADR | Title | Status |
|---|---|---|
| [000](#adr-000-repository-initialization) | Repository initialization | Accepted |
| [001](#adr-001-technology-stack) | Technology stack | Accepted |
| [002](#adr-002-authentication-and-identity-model) | Authentication and identity model | Proposed (not discussed) |
| [003](#adr-003-authorization-model) | Authorization model | Proposed (not discussed) |
| [004](#adr-004-retrieval-architecture) | Retrieval architecture | Proposed (not discussed) |
| [005](#adr-005-dataindexing-architecture) | Data / indexing architecture | Proposed (not discussed) |
| [006](#adr-006-llmprovider-selection) | LLM / provider selection | Proposed (not discussed) |
| [007](#adr-007-audit-log-design) | Audit-log design | Proposed (not discussed) |
| [008](#adr-008-deployment-architecture) | Deployment architecture | Proposed (not discussed) |

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
  (DEVELOPMENT.md section 9).

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
- Backend: FastAPI (Python 3.12, pip) in `backend/`; tests with pytest in
  `backend/tests/`.
- Database: PostgreSQL 17 with the pgvector extension, so documents,
  permissions, embeddings and the audit log live in one database.
- Local run: Docker Compose (`db`, `backend` on :8000, `frontend` on :3000).
- Still open: linter/formatter, Tencent Cloud services, LLM provider (ADR-006).

### Consequences

- Two runtimes (Node, Python), kept apart by folder; no monorepo tooling.
- One `docker compose up` runs everything; the database is not exposed to
  the host.

## ADR-002: Authentication and identity model

- **Status:** Proposed (not yet discussed)
- **Scope:** how a user is authenticated in the prototype; how one principal
  maps to Confluence, Jira, Slack and Google Drive identities; where group
  membership is resolved. Relates to SECURITY.md INV-3.

*Content to be added after team discussion.*

## ADR-003: Authorization model

- **Status:** Proposed (not yet discussed)
- **Scope:** where authorization is evaluated; how per-platform permission
  semantics are represented without flattening; how permission changes after
  ingestion are handled; deny-by-default. Relates to INV-1, INV-2, INV-4,
  INV-5, INV-8.

*Content to be added after team discussion.*

## ADR-004: Retrieval architecture

- **Status:** Proposed (not yet discussed)
- **Scope:** live API vs index vs hybrid; cross-platform fan-out and ranking;
  which connectors are real and which are mocked; behaviour when a source is
  unavailable.

*Content to be added after team discussion.*

## ADR-005: Data / indexing architecture

- **Status:** Proposed (not yet discussed)
- **Scope:** what is stored, how content is chunked/indexed, whether
  embeddings and a vector store are needed for the MVP, how permission
  metadata travels with indexed content, the freshness window and how it is
  achieved. Relates to INV-8 (stale permissions) and the data-freshness scenario.

*Content to be added after team discussion.*

## ADR-006: LLM / provider selection

- **Status:** Proposed (not yet discussed)
- **Scope:** provider and model; grounding and citation strategy;
  hallucination mitigation; what the model never sees. Relates to INV-1,
  INV-2, INV-9.

*Content to be added after team discussion.*

## ADR-007: Audit-log design

- **Status:** Proposed (not yet discussed)
- **Scope:** event schema (who / what / when / decision / answer); tamper-
  evidence mechanism; storage; query interface for the compliance persona;
  access control on the log itself. Relates to INV-6, INV-7.

*Content to be added after team discussion.*

## ADR-008: Deployment architecture

- **Status:** Proposed (not yet discussed)
- **Scope:** local-only vs hosted demo; whether a live link is submitted
  (optional, bonus points); which Tencent Cloud services, if any, are used;
  secrets handling in deployment.

*Content to be added after team discussion.*

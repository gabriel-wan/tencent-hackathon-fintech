# KnowBuddy

> Built for the Aspire challenge "The Internal Brain". Product name: **KnowBuddy**.

A permission-aware enterprise knowledge system that answers natural-language
questions across Confluence, Jira, Slack and Google Drive without ever showing
a user, or the LLM, content that user is not authorized to see, and keeps a
tamper-evident audit trail of who asked what, what was retrieved, and what was
answered.

| | |
|---|---|
| **Hackathon** | Tencent Cloud AI CAN DO IT Hackathon Singapore 2026 |
| **Track** | FinTech – Aspire |
| **Challenge** | The Internal Brain – Building a Context-Aware Enterprise Knowledge System with RBAC, Security Logging & Audit Trail |
| **Team** | Gabriel Wan, Vincent Ong, Liew Ze Wei |
| **Submission deadline** | **16 October 2026** |

## Problem

Enterprise knowledge is fragmented across wikis, tickets, chat and files, each
with its own permission model. An AI assistant that can read everything can
also leak everything. The challenge is to deliver unified, grounded answers
with citations while respecting every source platform's access controls,
staying fresh within a bounded window, and recording an auditable trail. Full
statement: [docs/hackathon/challenge.md](docs/hackathon/challenge.md).

## Current status

**Architecture decided (ADR-000 to ADR-009). End to end working locally: sign-in, the four connectors, sync, permission-filtered chat with citations, and a tamper-evident audit log.**

`docker compose up` runs Next.js, FastAPI and PostgreSQL/pgvector. People sign
in by connecting their own Slack, Google Drive, Jira or Confluence account
([connectors/GUIDE.md](docs/connectors/GUIDE.md)). Many companies can share one
deployment, each seeing only its own data. Sync copies each company's chosen
channels, folders, projects and spaces, with their permissions, every 5
minutes. A question is answered only from documents the asker may see,
confirmed live with each tool as that person, with citations
([QUERY_PIPELINE.md](docs/architecture/QUERY_PIPELINE.md)). Every question and
admin action goes into a per-company hash chain that admins can search and
verify (ADR-007). Fictional seed data is available for development.

Not built yet: the admin Audit and Boundary pages (the APIs exist; the pages
are previews with mock data), PII redaction, the prompt-injection test suite,
and the hosted deployment ([roadmap](docs/PROJECT.md#roadmap-and-status)).

## Architecture

How it's built, with diagrams of the trust boundary, the parts, one question and one sign-in:
[ARCHITECTURE.md](docs/ARCHITECTURE.md).
The non-negotiable security boundary:

```
USER → AUTHENTICATION → AUTHORIZATION → PERMISSION-AWARE RETRIEVAL
     → CONTEXT ASSEMBLY → LLM → ANSWER + CITATIONS
```

Authorization is evaluated by deterministic code that knows the user's
identity, **before** anything reaches the LLM. The LLM never decides who may
see what. Every stage emits audit events. Stack: Next.js, FastAPI,
PostgreSQL + pgvector (ADR-001); Tencent Cloud TokenHub for the LLM and
embeddings (ADR-006); one Tencent Cloud Lighthouse server for the live demo
(ADR-008). All decisions: [DECISIONS.md](docs/decisions/DECISIONS.md).

## Repository structure

```
.
├── README.md                this file
├── AGENTS.md                instructions for AI coding agents (CodeBuddy, WorkBuddy, Claude Code, ...)
├── CLAUDE.md                pointer to AGENTS.md
├── CONTRIBUTING.md          how the team works: branches, commits, PRs, reviews, decisions
├── .github/                 pull request template
├── docs/
│   ├── PROJECT.md           problem, users, scenarios, scope, roadmap and status
│   ├── SECURITY.md          threat model and security invariants
│   ├── README.md            map of the docs, and a glossary
│   ├── RUNNING.md           run and use it: settings, demo personas, your own tools, troubleshooting
│   ├── TESTING.md           backend, frontend, manual and accessibility checks
│   ├── ARCHITECTURE.md      how it's built: trust boundary, parts, flows, data model, trade-offs
│   ├── architecture/        deep dives: query pipeline, connectors, frontend
│   ├── connectors/          GUIDE.md (setup and API) and one page per tool
│   ├── decisions/
│   │   ├── DECISIONS.md     decision log (ADR-000 to ADR-009 accepted)
│   │   └── adr-template.md
│   └── hackathon/
│       ├── handbook.pdf     official handbook (source of truth)
│       ├── challenge.md     the Internal Brain challenge, organised
│       ├── requirements.md  mandatory requirements, timeline, judging, credits
│       ├── submission.md    submission checklist with deadline
│       ├── tool-usage.md    CodeBuddy/WorkBuddy usage log and checklist
│       └── evidence/        real screenshots / recordings, captured during development
├── docker-compose.yml       runs db, migrate, backend, sync and frontend
├── frontend/                Next.js app (localhost:3000), config in .env.example
├── backend/                 FastAPI app (localhost:8000), config in .env.example, tests in tests/, Alembic migrations in migrations/
└── scripts/                 helper scripts (check_doc_links.py: broken links in the docs)
```

## Development

Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to
`frontend/.env`, then `docker compose up --build`. Frontend at
http://localhost:3000, backend at http://localhost:8000/health. `.env` is
git-ignored and must never be committed. Step by step, with demo personas:
[RUNNING.md](docs/RUNNING.md). Testing: [TESTING.md](docs/TESTING.md). Every doc: [docs/README.md](docs/README.md).

## Security principles

Design principles, not claims about the implementation. Full list and threat
model in [SECURITY.md](docs/SECURITY.md).

- Unauthorized content never enters the LLM context.
- The LLM is never the component that decides authorization.
- Source-platform permission semantics are preserved, not flattened.
- Restricted content's existence is not revealed in negative cases.
- Permission changes are reflected within a stated freshness window.
- Every meaningful action produces a tamper-evident, queryable audit event.
- Retrieved content is untrusted data, never instructions.
- Secrets live only in the environment.

## Hackathon submission

- Deadline **16 Oct 2026**; finalists 23 Oct; Demo Day 3 Nov (TBC).
- The project must be built with **CodeBuddy or WorkBuddy**, with mandatory
  proof (3+ screenshots or a screen recording of development chat logs).
- Required: title, blurb under 10 words, description, source code on GitHub,
  16:9 cover image, tool-usage proof, worked examples for the five challenge
  scenarios, architecture and trust-boundary diagram. Optional: demo video,
  live link.
- Checklist: [docs/hackathon/submission.md](docs/hackathon/submission.md).
  Requirements: [docs/hackathon/requirements.md](docs/hackathon/requirements.md).

## For AI coding agents

Read [AGENTS.md](AGENTS.md) first, and the ADRs in
[DECISIONS.md](docs/decisions/DECISIONS.md) before touching authorization,
retrieval, LLM or audit code.

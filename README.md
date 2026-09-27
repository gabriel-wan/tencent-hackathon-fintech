# Internal Brain

> Working name taken from the challenge title. Final product name: **TBD**.

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
| **Team** | 3 students (TBD) |
| **Submission deadline** | **16 October 2026** |

## Problem

Enterprise knowledge is fragmented across wikis, tickets, chat and files, each
with its own permission model. An AI assistant that can read everything can
also leak everything. The challenge is to deliver unified, grounded answers
with citations while respecting every source platform's access controls,
staying fresh within a bounded window, and recording an auditable trail. Full
statement: [docs/hackathon/challenge.md](docs/hackathon/challenge.md).

## Current status

**Stack chosen (ADR-001). Skeleton running; no product features yet.**

`docker compose up` runs Next.js, FastAPI and PostgreSQL/pgvector, wired
together through a `/health` check. Nothing else described in this repository
is implemented yet. The documents lay out requirements, security principles,
open architectural questions and team conventions so that implementation can
start from a shared understanding.

## Planned architecture

Initial and subject to change; see [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md). The
non-negotiable security boundary:

```
USER → AUTHENTICATION → AUTHORIZATION → PERMISSION-AWARE RETRIEVAL
     → CONTEXT ASSEMBLY → LLM → ANSWER + CITATIONS
```

Authorization is evaluated by deterministic code that knows the user's
identity, **before** anything reaches the LLM. The LLM never decides who may
see what. Every stage emits audit events. Stack: Next.js, FastAPI,
PostgreSQL + pgvector (ADR-001). LLM provider and cloud services are still open
ADRs in [DECISIONS.md](docs/decisions/DECISIONS.md).

## Repository structure

```
.
├── README.md                this file
├── AGENTS.md                instructions for AI coding agents (CodeBuddy, WorkBuddy, Claude Code, ...)
├── CLAUDE.md                pointer to AGENTS.md
├── docs/
│   ├── PROJECT.md           problem, personas, scenarios, proposed MVP, open items
│   ├── SECURITY.md          threat model and security invariants
│   ├── DEVELOPMENT.md       setup, workflow, conventions, integrations, tests
│   ├── architecture/
│   │   ├── ARCHITECTURE.md  planned architecture, security boundary, open questions
│   │   └── CURRENT.md       diagram of what is built right now
│   ├── decisions/
│   │   ├── DECISIONS.md     decision log (ADR-000 and 001 accepted, 002–008 open)
│   │   └── adr-template.md
│   └── hackathon/
│       ├── handbook.pdf     official handbook (source of truth)
│       ├── challenge.md     the Internal Brain challenge, organised
│       ├── requirements.md  mandatory requirements, timeline, judging, credits
│       ├── submission.md    submission checklist with deadline
│       ├── tool-usage.md    CodeBuddy/WorkBuddy usage log and checklist
│       └── evidence/        real screenshots / recordings, captured during development
├── docker-compose.yml       runs db + backend + frontend
├── frontend/                Next.js app (localhost:3000), config in .env.example
├── backend/                 FastAPI app (localhost:8000), config in .env.example, tests in tests/, db/init.sql enables pgvector
└── scripts/                 helper scripts (empty)
```

## Development

Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to
`frontend/.env`, then `docker compose up --build`. Frontend at
http://localhost:3000, backend at http://localhost:8000/health. `.env` is
git-ignored and must never be committed. Details in
[DEVELOPMENT.md](docs/DEVELOPMENT.md).

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

Read [AGENTS.md](AGENTS.md) first. Do not write product code until the team
has reviewed ARCHITECTURE.md and recorded ADR-001.

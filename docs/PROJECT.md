# PROJECT.md – KnowBuddy

Product name **KnowBuddy**, built for the challenge "The Internal Brain" (the
name nods to Tencent's CodeBuddy and WorkBuddy).

| | |
|---|---|
| **Hackathon** | Tencent Cloud AI CAN DO IT Hackathon Singapore 2026 (co-hosted with AI Singapore) |
| **Track** | FinTech – Aspire |
| **Challenge** | The Internal Brain – Building a Context-Aware Enterprise Knowledge System with RBAC, Security Logging & Audit Trail |
| **Team** | Gabriel Wan, Vincent Ong, Liew Ze Wei |
| **Deadline** | Submission 16 Oct 2026; finalists 23 Oct; Demo Day 3 Nov (TBC) |
| **Status** | Architecture decided (ADR-000 to ADR-009). Working end to end locally: sign-in, four real connectors, sync, permission-filtered chat with citations, tamper-evident audit log. How it's built: [ARCHITECTURE.md](ARCHITECTURE.md) |

Authoritative challenge text: [docs/hackathon/challenge.md](hackathon/challenge.md).
Requirements and judging: [docs/hackathon/requirements.md](hackathon/requirements.md).

## Problem

Enterprise knowledge is fragmented across Confluence (wikis), Jira (issues),
Slack (conversation) and Google Drive (files). Each system has its own data
model and its own permission model. Nobody can hold it all, no single search
spans it, and no single access-control model governs it.

The challenge is not search. An AI assistant that can read everything can also
leak everything. The system must give unified, AI-assisted answers **while
respecting the permissions of the underlying systems**, staying fresh, and
keeping a tamper-evident record of who asked what, what was retrieved, and what
was answered.

## Target users

Candidate personas considered. The demo uses four (seeded as MerlionPay, and
planned as real demo accounts): **Priya** (admin and compliance: ADR-007 merges
the two), **Alice** (payments engineer), **Ben** (backend engineer) and
**Charlie** (external contractor, the negative persona).

| Persona | Why they matter for this challenge |
|---|---|
| Engineer (incl. on-call) | Primary asker; cross-references tickets, threads, runbooks, postmortems under time pressure |
| Manager / team lead | Asks for status and summaries across projects; broader but still bounded access |
| Compliance / security personnel | Consumes the audit trail; asks "who accessed what"; owns restricted spaces |
| Enterprise employee (general) | Everyday "where is the doc for X" questions |
| External contractor | The key *negative* persona: limited Slack presence, no Jira/Confluence access |
| Administrator | Manages connectors, permission sync, and audit tooling |

## Core value proposition

A permission-aware enterprise knowledge system that retrieves and synthesises
relevant information across multiple systems while preserving each system's
access controls and maintaining an auditable record of what happened.

## Core scenarios (from the handbook)

1. **Project status across Jira and Slack** – "What's the status of the
   database migration and were there blockers in Slack last week?" Answer
   synthesises Jira issues and Slack messages from channels the asker is in,
   with citations, and omits private channels they are not in.
2. **Incident / root-cause lookup** – "What was the root cause of the payment
   outage last quarter, and what follow-up tickets were created?" Also the
   freshness case: the runbook updated at 1:00 PM must be what the 2:05 PM
   query sees.
3. **Cross-referencing Jira, Slack, Confluence and Google Drive** – one answer
   built from a ticket, its Slack discussion, the Confluence decision doc and
   an attached Drive file, each piece individually permission-checked.
4. **Unauthorized request without leakage** – a contractor asks for the Q3
   breach report held in a security-team-only space. Nothing from the report
   is returned and its existence is neither confirmed nor denied.
5. **Auditing what a user accessed** – "Show me everything user `jdoe`
   accessed related to the `payment-gateway` Confluence space in the last 30
   days", answered from a tamper-evident log with timestamps and per-document
   decisions.

Each scenario needs a worked example in the submission and should map to a
demo step and to tests.

## MVP scope and status

The challenge requirements, and where each stands (ticked = built and covered
by tests; see [SECURITY.md](SECURITY.md) for the invariants behind them):

- [x] Unified natural-language query with citations across platforms (all four)
- [x] Permission-aware retrieval: identity known at query time; filtering
      **before** the LLM; per-platform permission semantics preserved
- [x] Negative permission case with no existence leak (same reply whether
      nothing exists or nothing is permitted)
- [x] Live permission change handling (each answer's sources are re-checked
      with each tool as the asker)
- [x] Data freshness within a bounded, stated window (about 5 minutes, plus
      "sync now"; each citation shows when it was last synced)
- [x] Audit log: complete (who / query / retrieved IDs / decisions / answer /
      timestamp), tamper-evident (per-company hash chain), queryable (search API)
- [ ] Audit inquiry interface for a compliance persona: the API is built; the
      admin Audit page still shows mock data
- [x] LLM leakage / hallucination mitigation (untrusted source blocks,
      citation checking, fixed reply when nothing is permitted)
- [ ] Trust-boundary diagram and architecture diagram for the submission
- [ ] Demo walkthrough covering all five scenarios, with real demo accounts

Questions the team answered:

- Real or mocked platforms: all four are real (ADR-004), against the team's own
  test workspaces filled with fictional data.
- Personas: Priya, Alice, Ben and Charlie (above).
- Freshness: sync every 5 minutes plus "sync now" (ADR-005); revocations apply
  on the next question through the live check (ADR-003).
- Admin and audit interface: an API plus admin pages (ADR-007).

## Roadmap and status

Status as of 8 October 2026, with the pull request that delivered each task. Task 1 is Vincent's, Task 2 Zewei's
and Task 3 Gabriel's ([CONTRIBUTING.md](../CONTRIBUTING.md) §7).

| Dates | Task | What | Status |
|---|---|---|---|
| 3–4 Oct | 1 | Jira, Confluence, Google Drive and Slack connectors; sync their data and permissions into the database | **Done** (#4) |
| 3–4 Oct | 2 | Frontend: sign-in, persona switcher, chat with answers and citations | **Done** (#6) |
| 3–4 Oct | 3 | Database schema, auth and permission filter, query pipeline (search → permission check → LLM answer) | **Done** (#5) |
| 5–6 Oct | 1 | Live permission changes and data freshness | **Done** (#10) |
| 5–6 Oct | 2 | Compliance/audit dashboard | **In progress**: the page exists with mock data; its API is in `main` since #11 |
| 5–6 Oct | 3 | Tamper-evident audit log and audit search API | **Done** (#11) |
| 7–8 Oct | 1 | PII redaction (Need-to-Know Shield) | **Not started** |
| 7–8 Oct | 2 | UI polish; show redaction and freshness in the UI | **Not started** (the API already returns each citation's `synced_at`) |
| 7–8 Oct | 3 | Prompt-injection protection; pass all 5 scenarios | **In progress**: retrieved text is fenced as untrusted and citations are checked; no dedicated injection tests or scenario run yet |
| 9–10 Oct | 1 | Deploy to Tencent Cloud (live link) | **Not started** |
| 9–10 Oct | 2 | Demo video and cover image | **Not started** |
| 9–10 Oct | 3 | Tests, bug fixes and docs | **In progress** (with each pull request; docs restructure in progress) |
| 11–12 Oct | 1 | Final testing on a clean machine | **Not started** |
| 11–12 Oct | 2 | Project description and diagrams | **Not started** |
| 11–12 Oct | 3 | Collect the CodeBuddy/WorkBuddy screenshots and submit | **Not started**: the evidence log is still empty, and without proof the project is not scored |
| 13–16 Oct | | Buffer | |

### Planned UI work

What the frontend does next, and what each item waits for:


| Waiting on | UI work |
|---|---|
| Nothing (the API exists) | Real `/admin/boundary` on the boundary API: list scopes per tool, add and remove them, "Sync now" |
| Nothing | Show which sources are connected in the chat |
| Return target after the OAuth callback | Show sign-in errors on `/login` rather than `/connectors`. The target must come from a fixed allowlist, never an arbitrary URL (open redirect) |
| `label` on each citation | Turn `[S1]` markers into chips linked to the right source (today they are stripped: an answer citing `[S1]` and `[S3]` came back with two citations, so mapping by position would be wrong) |
| `status` on query responses | Classify answers by status instead of matching the fixed sentences |
| Nothing (the API exists) | Real `/admin/audit` (search, verify chain); make "Ref #" a link for admins |
| Something to poll after `POST /api/admin/sync` (`synced_at` on citations and `last_synced_at` on the boundary already exist) | "Synced N minutes ago" under answers and after "Sync now", for the freshness demo (scenario 2) |
| A company field on `GET /api/me` | Tell "you have no company yet" apart from "nothing found" (today `/connectors` only infers it from the connections) |
| Redaction and injection flags (7–8 Oct) | Redaction chip on citations; blocked-injection notice on answers |

Each replaces a stub or a reserved slot; remove the matching "Not built yet"
panel and design preview in the same PR.

## Out of scope for the hackathon (proposed)

- Production-grade identity federation with real enterprise IdPs
- Full coverage of every permission edge case in all four platforms
- Horizontal scalability and high availability (several companies per deployment is built, ADR-002)
- Anything that requires infrastructure the team cannot run locally or demo reliably

## Open items (everything marked TBD)

| Item | Where |
|---|---|
| Linter / formatter | DECISIONS.md ADR-001 |
| Track-specific judging criteria (if received) | docs/hackathon/requirements.md |

**Questions for the team** (raised while building; each answer goes into DECISIONS.md or the code, and each can
become a GitHub issue labelled `question`):

| For | Question |
|---|---|
| Whole team | May the audit page show titles of documents the admin cannot read? (the original ARCHITECTURE.md §3.12 vs ADR-007.) Until decided, documents are shown by key |
| Whole team | Demo accounts: which Google accounts are OAuth test users (Testing-mode tokens expire after 7 days)? A Google-only contractor no longer works (Google names no company), and Slack guests need a paid plan: how does the demo show the contractor? |
| Query pipeline | Add `label` and `status` to the query response; should a 503 "LLM is not configured" become the fixed "unavailable" reply? |
| Query pipeline | Without an LLM configured, `/api/query` returns 503 before the pipeline runs, so the question is not audited. Should it be? |
| Connectors | A fixed-allowlist return target after sign-in, so a successful sign-in can land in the chat; what happens when someone disconnects their last connection; can personal Gmail users get `google:domain:gmail.com` as a principal? |
| Connectors | `GET /api/me` has no company field, and `POST /api/admin/sync` gives nothing to poll (only each scope's `last_synced_at`): can both be added? |


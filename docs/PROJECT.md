# PROJECT.md – KnowBuddy

**For:** anyone who wants the why: the problem, the users, the scope, and how far along we are.
**You'll:** see the challenge's scenarios, what's in and out of scope, the roadmap with each task's status, planned
work and open questions.
**Not here:** each scenario working → [FEATURES.md](FEATURES.md) · how it's built → [ARCHITECTURE.md](ARCHITECTURE.md).

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
- [x] Audit inquiry interface for a compliance persona: the admin Audit page
      searches, pages and verifies the trail through the API
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

Status as of 11 October 2026, with the pull request that delivered each task. Task 1 is Vincent's, Task 2 Zewei's
and Task 3 Gabriel's ([CONTRIBUTING.md](../CONTRIBUTING.md) §7).

| Dates | Task | What | Status |
|---|---|---|---|
| 3–4 Oct | 1 | Jira, Confluence, Google Drive and Slack connectors; sync their data and permissions into the database | **Done** (#4) |
| 3–4 Oct | 2 | Frontend: sign-in, persona switcher, chat with answers and citations | **Done** (#6) |
| 3–4 Oct | 3 | Database schema, auth and permission filter, query pipeline (search → permission check → LLM answer) | **Done** (#5) |
| 5–6 Oct | 1 | Live permission changes and data freshness | **Done** (#10) |
| 5–6 Oct | 2 | Compliance/audit dashboard | **Done**: `/admin/audit` searches the trail (filters in the URL, every event type), opens each record and verifies the chain |
| 5–6 Oct | 3 | Tamper-evident audit log and audit search API | **Done** (#11) |
| 7–8 Oct | 1 | PII redaction (Need-to-Know Shield) | **Done** (#16) |
| 7–8 Oct | 2 | UI polish; show redaction and freshness in the UI | **Done**: the Boundary page; under answers, a "N masked" chip per source, the blocked-injection notice and "synced N minutes ago"; tool logos; "Ref #" links to the audit record for admins |
| 7–8 Oct | 3 | Prompt-injection protection; pass all 5 scenarios | **In progress**: prompt-injection protection built (ADR-011: fence, scanner, link check, `test_injection.py`, a live check against `hy3`); the 5-scenario run with real demo data is next |
| 9–10 Oct | 1 | Deploy to Tencent Cloud (live link) | **Done** (#23, #24): live at <https://knowbuddy.xyz> with Slack, Google Drive and Jira/Confluence sign-in, and every merge to main deploys itself after CI passes ([DEPLOYMENT.md](DEPLOYMENT.md)). Only the Atlassian app's owner (the demo admin) can connect Jira and Confluence until the app is shared |
| 9–10 Oct | 2 | Demo video and cover image | **In progress**: the cover image is done ([hackathon/cover.png](hackathon/cover.png), made with Miora); the demo video is not started |
| 9–10 Oct | 3 | Tests, bug fixes and docs | **In progress** (with each pull request; docs restructure in progress). CI runs every test on each pull request, and main only merges green (#24) |
| 11–12 Oct | 1 | Final testing on a clean machine | **Not started** |
| 11–12 Oct | 2 | Project description and diagrams | **Not started** |
| 11–12 Oct | 3 | Collect the CodeBuddy/WorkBuddy screenshots and submit | **In progress**: the minimum is met (3 CodeBuddy sessions, 6 screenshots, [tool-usage.md](hackathon/tool-usage.md)), plus a Miora session for the cover; the submission itself is not done |
| 15–16 Oct | 2 | Audit assistant: ask the audit trail in plain language (ADR-013, [build plan](#planned-audit-assistant)) | **Not started**: ADR-013 proposed, waiting for review |
| 13–16 Oct | | Buffer | |

### Planned: audit assistant

ADR-013 (Proposed) says what it does and why; this is the order it's built in. Branch `feat/audit-assistant`, one
sub-branch per phase, merged `--no-ff` ([CONTRIBUTING.md](../CONTRIBUTING.md)). Zewei builds every phase, backend
and frontend; Gabriel and Vincent review the pull request, since it changes what the LLM receives.

| Phase | What | Files | Done when |
|---|---|---|---|
| A. Plan and resolve | The planner prompt and its JSON parse; validate each value as `GET /api/admin/audit` does; resolve people, scopes and documents within the admin's company, or return a clarifying question | `backend/app/audit/assistant.py`, `backend/tests/test_audit_assistant.py`; `FakeLLM` takes a list of replies (plan, then summary) | Tests: bad values dropped, a `company_id` in the plan is ignored, another company's names never resolve, an ambiguous name asks |
| B. Facts and summary | Count the matches; build `<record>` blocks (masked text, decisions; no hashes, principals or ACLs); fence and `strip_blocks`; the summary prompt; `ground()`; labels back to record numbers | the same files | Tests: what a block holds and omits, an injected logged question is removed and reported, invented labels removed, no valid citation gives the fixed reply |
| C. Endpoint and audit event | `POST /api/admin/audit/ask`, admins only; one `audit_asked` event per question, also when the LLM fails | `backend/app/audit/api.py`, `backend/tests/test_audit.py` | Tests: 403 for non-admins, the event's fields, an LLM error still records the event; `schema.d.ts` regenerated |
| D. Ask panel | Ask box above the table on `/admin/audit`; answer with `[S<n>]` chips opening the record dialog, the facts, the filters used as chips, "Open in audit trail"; `audit_asked` in the event list and record dialog; mock mode labelled as mocked | `frontend/components/admin/audit-ask.tsx`, `frontend/lib/audit.ts`, `frontend/lib/api/client.ts`, `frontend/lib/api/mock.ts` | Vitest for label mapping and filters-to-URL; checked in the browser with the seeded personas |
| E. Docs and live check | SECURITY.md §3, INV-6 and INV-9; ARCHITECTURE.md; QUERY_PIPELINE.md; FEATURES.md scenario 5; FRONTEND.md. Run the challenge's audit inquiry and a planted-instruction question against `hy3` and note the results in ADR-013 | `docs/` | `python3 scripts/check_doc_links.py` passes; ADR-013 accepted after review |

If time runs out, A–C with the table's existing filters still answer scenario 5 through the API; D is what the demo
shows.

### Planned UI work

What the frontend does next, and what each item waits for:


| Waiting on | UI work |
|---|---|
| Nothing | Show which sources are connected in the chat |
| Return target after the OAuth callback | Show sign-in errors on `/login` rather than `/connectors`. The target must come from a fixed allowlist, never an arbitrary URL (open redirect) |
| `status` on query responses | Classify answers by status instead of matching the fixed sentences |
| A company field on `GET /api/me` | Tell "you have no company yet" apart from "nothing found" (today `/connectors` only infers it from the connections) |

Each fills a reserved slot in the UI.

### Planned scaling work

For the handbook's Company A ([ARCHITECTURE.md](ARCHITECTURE.md#how-it-scales) says what already scales). Not built;
after the submission unless the team decides otherwise.

| Work | Why | Suggested owner |
|---|---|---|
| **Incremental sync:** list only what changed since the last run (Confluence CQL `lastmodified`, Jira JQL `updated`, Slack `oldest`, Drive's Changes API), with a full reconcile nightly for deletions and permission changes | Full listing of 12,000 pages and 200+ channel histories every 5 minutes doesn't fit the window or the rate limits | Vincent |
| **Parallel, rate-aware sync:** a small worker pool per tool, honouring `Retry-After`, most out-of-date scopes first | One huge space mustn't starve the rest | Vincent |
| **Drive shared drives:** take access from the shared drive's members | Shared-drive files are skipped today | Vincent (permission model: tests and a SECURITY.md update) |
| **Search load test** at ~100k chunks with realistic ACLs; maybe a `documents.in_boundary` column | Check the HNSW + permission filter still returns enough results quickly | Gabriel |
| **Audit at volume:** indexes for the document and scope filters; verify the chain from a saved checkpoint | Those filters scan JSON; `verify_chain` reads the whole chain | Gabriel |
| **Several Slack workspaces** in one company (needs an ADR) | Enterprise Grid | Vincent |
| **Jira issue security levels** stored with each ticket | Today the live check trims them at question time, which is correct but does more work at scale | Vincent |

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


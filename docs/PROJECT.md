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
| **Status** | Architecture decided (ADR-000 to ADR-008). Working end to end locally: sign-in, four real connectors, sync, permission-filtered chat with citations, tamper-evident audit log. Built state: [CURRENT.md](architecture/CURRENT.md) |

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

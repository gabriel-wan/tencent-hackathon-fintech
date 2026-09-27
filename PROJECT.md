# PROJECT.md – Internal Brain

Working name **Internal Brain** (taken from the challenge title). Final product
name: **TBD**.

| | |
|---|---|
| **Hackathon** | Tencent Cloud AI CAN DO IT Hackathon Singapore 2026 (co-hosted with AI Singapore) |
| **Track** | FinTech – Aspire |
| **Challenge** | The Internal Brain – Building a Context-Aware Enterprise Knowledge System with RBAC, Security Logging & Audit Trail |
| **Team** | 3 students (names TBD in this file) |
| **Deadline** | Submission 16 Oct 2026; finalists 23 Oct; Demo Day 3 Nov (TBC) |
| **Status** | Stack chosen (ADR-001); running skeleton with health check only; no product features |

Authoritative challenge text: [docs/hackathon/challenge.md](docs/hackathon/challenge.md).
Requirements and judging: [docs/hackathon/requirements.md](docs/hackathon/requirements.md).

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

Candidate personas, **not yet locked in**. The team will pick a small number to
design and demo around.

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

## Proposed MVP – To Be Finalized

**This section is a proposal for team discussion, not a decision.** The
challenge requirements below are what we must prioritise; how much of each
lands in the MVP is the team's call and will be recorded in DECISIONS.md.

Requirements we must prioritise (from the challenge):

- [ ] Unified natural-language query with citations across at least two platforms
- [ ] Permission-aware retrieval: identity known at query time; filtering
      **before** the LLM; per-platform permission semantics preserved
- [ ] Negative permission case with no existence leak
- [ ] Live permission change handling (revocation reflected on next query)
- [ ] Data freshness within a bounded, stated window
- [ ] Audit log: complete (who / query / retrieved IDs / decisions / answer /
      timestamp), tamper-evident, queryable
- [ ] Audit inquiry interface for a compliance persona
- [ ] LLM leakage / hallucination mitigation (grounding, citations, refusal
      when context is empty)
- [ ] Trust-boundary diagram and architecture diagram (required deliverable)
- [ ] Demo walkthrough covering all five scenarios

Open MVP questions for the team:

- Which platforms are integrated for real and which are mocked with realistic
  permission models? (Mocks must be labelled as mocks.)
- Which two or three personas do we demo?
- What freshness window do we commit to, and how is it achieved?
- What is the minimum admin/audit UI: a page, a CLI, or an API?

## Out of scope for the hackathon (proposed)

- Production-grade identity federation with real enterprise IdPs
- Full coverage of every permission edge case in all four platforms
- Horizontal scalability, multi-tenancy, high availability
- Anything that requires infrastructure the team cannot run locally or demo reliably

## Open items (everything marked TBD)

| Item | Where |
|---|---|
| Final product name | README.md, PROJECT.md |
| Team member names and roles | PROJECT.md |
| Personas to design around | PROJECT.md |
| MVP scope | PROJECT.md |
| Authentication / identity model | DECISIONS.md ADR-002 |
| Authorization model | DECISIONS.md ADR-003 |
| Retrieval architecture | DECISIONS.md ADR-004 |
| Data / indexing architecture | DECISIONS.md ADR-005 |
| LLM / provider selection | DECISIONS.md ADR-006 |
| Audit-log design | DECISIONS.md ADR-007 |
| Deployment architecture | DECISIONS.md ADR-008 |
| Track-specific judging criteria (if received) | docs/hackathon/requirements.md |
| Which Tencent Cloud services, if any, are adopted | docs/hackathon/tool-usage.md, DECISIONS.md |

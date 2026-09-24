# Challenge: The Internal Brain

**Track:** FinTech – Aspire
**Hackathon:** Tencent Cloud AI CAN DO IT Hackathon Singapore 2026
**Full title:** The Internal Brain – Building a Context-Aware Enterprise Knowledge System with RBAC, Security Logging & Audit Trail
**Source:** Official hackathon handbook, section 4 ([handbook.pdf](handbook.pdf)). This file organises that section; where wording matters, read the original.

> The handbook requires each team to choose exactly one case study and to state
> the chosen case study at the start of the presentation. Ours is this one.

## 1. The problem as Aspire frames it

Enterprise knowledge is scattered across four platforms, each with its own
data model, API, pagination, rate limits and permission semantics:

| Platform | Role in the enterprise | Permission model (per handbook) |
|---|---|---|
| Confluence | Wikis and documentation | Space-level and page-level; some pages restricted to named individuals |
| Jira | Issue tracking and project management | Project + role + issue-level security (e.g. security bugs visible only to the security team) |
| Slack | Real-time communication, deeply nested threads | Channel membership, including private channels and DMs; retention policies |
| Google Drive | File storage and collaboration | File- and folder-level sharing (view/comment/edit); some external sharing |

The illustrative "Company A" has 50+ Confluence spaces and 12,000+ pages,
30+ Jira projects, 200+ Slack channels across multiple workspaces, and shared
plus personal Drives. Employees reportedly lose roughly 30% of their week
searching for information.

The CTO wants an assistant that can answer questions such as:

- the root cause of last quarter's payment outage and the follow-up tickets;
- a summary of last sprint's Slack design discussion on the new auth service,
  linked to the Confluence decision doc.

The hard constraint the CTO raises: **if the assistant can read everything,
can it leak everything?** A junior engineer asking for "all security
vulnerabilities" must not receive security-team-only Confluence pages. An
external contractor in Slack must not query internal Jira. Every answer must
be scoped to the asker's actual authorization, with a tamper-evident record of
every retrieval and every answer.

The handbook is explicit that this is *not* "a chatbot bolted onto search" but
a governed, permission-aware knowledge fabric with an LLM reasoning layer.

## 2. What the system must do (challenge requirements)

### 2.1 Heterogeneous source integration
Build a unified ingestion and retrieval layer across all four platforms that
**does not flatten away** their differing permission semantics. Flattening
them is described as breaking access control.

### 2.2 Permission-aware retrieval
The retrieval pipeline must:

- know the identity and roles/permissions of the asker **at query time**;
- **filter candidate documents before they reach the LLM**, so the model never
  sees content the user may not see. The handbook gives two reasons: answer
  leakage, and prompt injection via retrieved content;
- **handle permission changes**: if access to a page is revoked between
  ingestion and query, stale-permitted content must not be served.

### 2.3 Context assembly across platforms
One answer may need a Jira ticket, its linked Slack discussion, the related
Confluence doc and an attached Drive file. The retrieval strategy must fan out
across platforms, rank cross-platform results and assemble a coherent context
window, respecting per-platform permissions on every constituent piece.

### 2.4 Security logging and audit trail
Every meaningful action must be recorded so that the record is:

- **tamper-evident** – an auditor can detect modification or deletion;
- **complete** – who (identity), what (query, retrieved document IDs, final
  answer), when (timestamp), and the authorization decision per document
  (allowed/denied);
- **queryable** – e.g. "what did user X access last week", "who retrieved this
  sensitive doc".

### 2.5 LLM safety in a permissioned world
Even with correct filtering, the model may hallucinate, paraphrase restricted
content from training data, or confabulate. The solution must mitigate the
risk that the model "fills in" content it was not given.

## 3. Scenarios the solution must demonstrably solve

The handbook says each scenario must be accompanied by a **worked example in
the submission**. These map directly to demo script items and to tests.

| # | Scenario | Handbook example | What "pass" looks like |
|---|---|---|---|
| 1 | **Unified natural-language query** | Backend engineer asks for database-migration status and last week's Slack blockers | System picks relevant platforms, retrieves permission-filtered context, returns one grounded answer **with citations**, omitting private-channel threads the engineer is not in |
| 2 | **Data freshness** | Runbook updated at 1:00 PM; on-call engineer asks at 2:05 PM | The updated runbook (with the new failover step) is surfaced, not the morning's cached version. Bounded, predictable window "on the order of minutes to ~1 hour" |
| 3 | **Correct permission enforcement (negative cases)** | Contractor asks for the Q3 breach incident report held in a security-team-only space | Answer contains none of the report and **does not confirm or deny its existence** beyond what the user's permissions already imply (no metadata side-channel) |
| 4 | **Live permission change handling** | User removed from a Slack channel, or a Confluence page becomes restricted | Subsequent queries reflect the change; content the user can no longer access is not served |
| 5 | **Audit inquiry** | "Show me everything user `jdoe` accessed related to the `payment-gateway` Confluence space in the last 30 days" | Compliance officer can reconstruct what a user asked, what was retrieved, what was answered, with timestamps and authorization decisions |

## 4. Required deliverables ("The Solution Should Include")

- **Demo walkthrough** – a live demonstration.
- **Architecture diagram** – architecture, **trust-boundary diagram**, and key
  design trade-offs.
- **Source code** – complete source code in a GitHub repository.

## 5. Notes on the handbook text

- The handbook states that the listed features are guidance and that teams are
  encouraged to explore alternative approaches that meaningfully address the
  problem. The five scenarios above are nonetheless phrased as "must".
- The "The Solution Should Be" bullet list printed under the FinTech track in
  the handbook (empowering, personalised, longitudinal, patients, medication,
  pharmacist) is clearly the Healthcare track's text repeated by mistake. It is
  **not** treated as a FinTech requirement here. If Aspire or Tencent issue a
  correction, update this file.
- Track-specific detailed judging criteria are, per the handbook, shared after
  registration. See [requirements.md](requirements.md) for what is known now.

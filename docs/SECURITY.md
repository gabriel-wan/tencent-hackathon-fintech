# SECURITY.md

> **Status: design principles.** Everything in this document describes what the
> system is *meant* to guarantee. Nothing here is a claim that the
> implementation already satisfies it. As invariants gain tests, link the tests
> here.

Security is the core of this challenge, not a feature. The handbook's framing:
an assistant that can read everything can leak everything, so every answer must
be scoped to what the asker is authorized to see, with a tamper-evident record.

## 1. Threat model

### Assets
- Content in Confluence, Jira, Slack and Google Drive, including restricted
  spaces, issue-level-secured tickets, private channels, DMs and shared files.
- The *existence* and metadata of restricted content (titles, authors, counts).
- User identities and permission data.
- The audit log itself.
- Connector credentials and LLM API keys.

### Actors
- Legitimate users with varying access (engineer, manager, contractor, admin,
  compliance).
- A curious or malicious insider probing for content beyond their access.
- An external party who can plant content in a source system (e.g. a
  contractor posting in Slack, an external Drive share).
- A compromised or over-privileged component of our own system.

### Threats

| # | Threat | Description | Primary mitigations (design intent) |
|---|---|---|---|
| T1 | Prompt injection (direct) | User query contains instructions to ignore rules or reveal hidden context | LLM never holds authority over authorization; system prompt hygiene; output grounding |
| T2 | Indirect prompt injection via retrieved content | A document, ticket, message or file contains instructions aimed at the model | Only authorized content reaches the model; content treated as data; citations and grounding; limit tool/action capabilities of the model |
| T3 | Unauthorized retrieval | Retrieval returns content the asker may not see | Deterministic authorization evaluated before context assembly; deny by default |
| T4 | Permission changes after ingestion | Access revoked or a page restricted after indexing; index still says "allowed" | Permission re-validation at query time and/or bounded permission-sync window; treat cached permissions as hints, not decisions |
| T5 | Data leakage through answers | Model paraphrases or summarises restricted content it should not have had | Same as T3/T4 plus answer grounding checks |
| T6 | Cross-user information leakage | Caches, conversation memory, embeddings or logs leak one user's context to another | No shared caches of assembled context across identities; per-user scoping of any memory |
| T7 | Stale permission metadata | Index metadata lags the source platform | Freshness window applies to permissions as well as content; explicit staleness budget |
| T8 | Hallucinated information | Model invents facts, tickets, people or citations | Answer only from provided context; cite every claim; refuse or say "not found" when context is empty; verify citations exist |
| T9 | Existence side-channel | System reveals that a restricted document exists (counts, "access denied to X", ranking effects) | Negative responses indistinguishable from "nothing found" beyond what the user's own permissions already imply |
| T10 | Audit-log tampering | Entries modified or deleted to hide access | Tamper-evident structure (e.g. hash chaining or signing, exact mechanism TBD in ADR-007); append-only storage; separate write path |
| T11 | Credential / API-key leakage | Secrets in code, logs, screenshots, chat logs, prompts | `.gitignore`, env-only secrets, redaction in logs and evidence screenshots, no secrets in prompts |
| T12 | Malicious or untrusted enterprise content | Files with active content, oversized inputs, malformed data | Content is parsed defensively and never executed; size and type limits |
| T13 | Over-privileged connectors | A connector credential can read more than any user should; a bug in our code becomes a leak | Least-privilege connector scopes; authorization is our layer's job regardless of what the connector can technically read |

## 2. Security invariants

These are the rules the design must uphold. Each should eventually have at
least one automated test. Until then they are **principles, not guarantees**.

| ID | Invariant | Test status |
|---|---|---|
| INV-1 | An unauthorized document, message, ticket or file must never be included in LLM context, in whole, in part, or as embeddings-derived summary. | not yet tested |
| INV-2 | The LLM must not be the component that decides whether a user is authorized. Authorization is evaluated by deterministic code before context assembly. | not yet tested |
| INV-3 | User identity must be available and verified at the moment authorization is evaluated. No anonymous or "system" retrieval on a user's behalf. | not yet tested |
| INV-4 | Authorization decisions are deterministic and inspectable: given the same user, document and permission state, the decision is the same, and the reason is recorded. | not yet tested |
| INV-5 | The existence of restricted content is not unnecessarily revealed. A denied or filtered item must not change the response in a way that leaks beyond what the user's permissions already imply. | not yet tested |
| INV-6 | Audit events capture enough to reconstruct important access decisions: identity, timestamp, query, candidate and retrieved document IDs, per-document decision and reason, final answer (or a reference to it). | not yet tested |
| INV-7 | Audit records are tamper-evident: modification or deletion of any record is detectable by an auditor. | not yet tested |
| INV-8 | A permission revocation in a source platform is reflected in query results within the stated freshness window, and never later than that. | not yet tested |
| INV-9 | Retrieved content is treated as untrusted data. It is never executed and never allowed to change authorization, tool selection or audit behaviour. | not yet tested |
| INV-10 | Secrets exist only in the environment. None are in source, tests, fixtures, logs, prompts or committed evidence. | not yet tested |

## 3. What the LLM must never see

- Content the asking user is not authorized to view (INV-1).
- Connector credentials, API keys, signing keys.
- Other users' queries, contexts or answers.
- Raw permission tables or ACLs beyond what is needed to answer (ideally none).
- Audit-log internals such as hashes or signatures.

## 4. Handling denied access

Design intent, to be validated with the team:
- Filter silently at retrieval time; the answer is built only from allowed items.
- If nothing allowed remains, respond as "no relevant information found for
  you", not "access denied to <title>".
- Log the denial with the reason in the audit trail, where the compliance
  persona can see it. The asker does not see it.

## 5. Reporting a security issue during the hackathon

Tell the team immediately in the team channel and open an issue labelled
`security`. Do not push a fix that changes security behaviour without a review
from a second team member (see DEVELOPMENT.md).

# SECURITY.md

**For:** anyone changing how KnowBuddy decides who sees what, and judges checking the security claims.
**You'll:** see the threats, the rules KnowBuddy must never break, and which tests guard each rule.
**Not here:** where each rule is enforced in the code → [ARCHITECTURE.md](ARCHITECTURE.md) §2 · running the security
tests → [TESTING.md](TESTING.md) §1 and §3.

> **What this is:** the guarantees the system must give. The threat model and
> invariants are design statements; the **Test status** column in section 2
> says, for each invariant, what is built and which tests prove it. A guarantee
> counts only once its status says so.

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
| T4 | Permission changes after ingestion | Access revoked or a page restricted after indexing; index still says "allowed" | Permission re-validation at query time and/or bounded permission-sync window; treat cached permissions as hints, not decisions. Built: every question is live-checked with each source as the user (`app/connectors/live.py`) |
| T5 | Data leakage through answers | Model paraphrases or summarises restricted content it should not have had | Same as T3/T4 plus answer grounding checks. Built: the Need-to-Know Shield masks sensitive identifiers before the LLM and masks any the answer contains that the user was not shown (ADR-010, `app/redaction.py`) |
| T6 | Cross-user information leakage | Caches, conversation memory, embeddings or logs leak one user's context to another | No shared caches of assembled context across identities; per-user scoping of any memory |
| T7 | Stale permission metadata | Index metadata lags the source platform | Freshness window applies to permissions as well as content; explicit staleness budget. Built: every sync (5 min) refreshes every stored ACL; syncs of one company never overlap; each citation carries `synced_at`, so a scope that stopped syncing is visibly stale |
| T8 | Hallucinated information | Model invents facts, tickets, people or citations | Answer only from provided context; cite every claim; refuse or say "not found" when context is empty; verify citations exist |
| T9 | Existence side-channel | System reveals that a restricted document exists (counts, "access denied to X", ranking effects) | Negative responses indistinguishable from "nothing found" beyond what the user's own permissions already imply |
| T10 | Audit-log tampering | Entries modified or deleted to hide access | Tamper-evident structure; append-only storage; separate write path. Built (ADR-007): one hash chain per company, an app database role that can only read and add audit records, and triggers that stop even the owner (INV-7) |
| T11 | Credential / API-key leakage | Secrets in code, logs, screenshots, chat logs, prompts | `.gitignore`, env-only secrets, redaction in logs and evidence screenshots, no secrets in prompts. Built: secrets in documents and in the question are masked before the LLM, the embedding model and the audit log (ADR-010) |
| T12 | Malicious or untrusted enterprise content | Files with active content, oversized inputs, malformed data | Content is parsed defensively and never executed; size and type limits |
| T13 | Over-privileged connectors | A connector credential can read more than any user should; a bug in our code becomes a leak | Least-privilege connector scopes; authorization is our layer's job regardless of what the connector can technically read |

## 2. Security invariants

These are the rules the design must uphold. Each should eventually have at
least one automated test. Until then they are **principles, not guarantees**.

| ID | Invariant | Test status |
|---|---|---|
| INV-1 | An unauthorized document, message, ticket or file must never be included in LLM context, in whole, in part, or as embeddings-derived summary. | Tested: [test_query_pipeline.py](../backend/tests/test_query_pipeline.py), [test_search.py](../backend/tests/test_search.py) (including company isolation), live checks per source ([test_sync.py](../backend/tests/test_sync.py), [test_slack.py](../backend/tests/test_slack.py), [test_drive.py](../backend/tests/test_drive.py), [test_atlassian.py](../backend/tests/test_atlassian.py)) |
| INV-2 | The LLM must not be the component that decides whether a user is authorized. Authorization is evaluated by deterministic code before context assembly. | Tested: [test_search.py](../backend/tests/test_search.py), [test_live_check.py](../backend/tests/test_live_check.py) |
| INV-3 | User identity must be available and verified at the moment authorization is evaluated. No anonymous or "system" retrieval on a user's behalf. | Tested: session-only identity ([test_api.py](../backend/tests/test_api.py)); connector sign-in joins only the company of its Slack workspace or Atlassian site ([test_connections_api.py](../backend/tests/test_connections_api.py)) |
| INV-4 | Authorization decisions are deterministic and inspectable: given the same user, document and permission state, the decision is the same, and the reason is recorded. | Partly: per-document decision and reason recorded in the audit log ([test_query_pipeline.py](../backend/tests/test_query_pipeline.py)) |
| INV-5 | The existence of restricted content is not unnecessarily revealed. A denied or filtered item must not change the response in a way that leaks beyond what the user's permissions already imply. | Partly: filter runs before ranking; same reply for nothing found and nothing permitted ([test_query_pipeline.py](../backend/tests/test_query_pipeline.py)) |
| INV-6 | Audit events capture enough to reconstruct important access decisions: identity, timestamp, query, candidate and retrieved document IDs, per-document decision and reason, final answer (or a reference to it). | Partly: query events ([test_query_pipeline.py](../backend/tests/test_query_pipeline.py)) and boundary changes ([test_admin.py](../backend/tests/test_admin.py)) tested, as are connector connect/disconnect events ([test_connections_api.py](../backend/tests/test_connections_api.py)), "sync now" ([test_admin.py](../backend/tests/test_admin.py)) and audit searches and verifications ([test_audit.py](../backend/tests/test_audit.py)). The admin can search the trail by user, time, event type, document, tool and scope (`GET /api/admin/audit`, [test_audit.py](../backend/tests/test_audit.py)) |
| INV-7 | Audit records are tamper-evident: modification or deletion of any record is detectable by an auditor. | Built: one hash chain per company, recomputed by `POST /api/admin/audit/verify`, which reports the first changed, deleted or reordered record; the app logs in as its own database role, which can only read and add records and cannot switch to a more powerful role (`SET ROLE NONE` included); triggers stop even the owner ([test_audit.py](../backend/tests/test_audit.py)). Limitation: someone with the owner's login could rewrite every later record too, so note the chain's head (returned by verify) outside the system (ADR-007) |
| INV-8 | A permission revocation in a source platform is reflected in query results within the stated freshness window, and never later than that. | Partly: the live check asks all 4 sources as the user on every question (unit-tested with fakes), so a revocation applies on the next question; Drive files in the trash are denied too ([test_drive.py](../backend/tests/test_drive.py)). Known limits: a deleted Slack message (its channel still readable) drops at the next sync (≤ 5 min); a revocation landing in the seconds between the live check and the answer applies to the next question. Not yet verified against real workspaces. Development personas without a connection still use the stored-ACL stub |
| INV-9 | Retrieved content is treated as untrusted data. It is never executed and never allowed to change authorization, tool selection or audit behaviour. | Partly: retrieved text cannot break out of its source block ([test_grounding.py](../backend/tests/test_grounding.py)) |
| INV-10 | Secrets exist only in the environment. None are in source, tests, fixtures, logs, prompts or committed evidence. | not yet tested |
| INV-11 | Sensitive identifiers (cards, NRIC/FIN, bank accounts, IBANs, passports, dates of birth, phones, emails and names except colleagues', Singapore addresses) in an authorized document reach the LLM, the embedding model and the user only masked, unless the source names the user as that document's handler. Secrets are masked for everyone. Hidden (zero-width) and full-width characters do not get an identifier past the masking. A person's name found once (honorific or person label) is masked in every mention, labelled or not. The audit log records counts, never values, and stores the question and answer fully masked, including any value the user was shown unmasked. | Tested: [test_redaction.py](../backend/tests/test_redaction.py), [test_query_pipeline.py](../backend/tests/test_query_pipeline.py), [test_sync.py](../backend/tests/test_sync.py), [test_drive.py](../backend/tests/test_drive.py) |

## 3. What the LLM must never see

- Content the asking user is not authorized to view (INV-1).
- Connector credentials, API keys, signing keys.
- Other users' queries, contexts or answers.
- Raw permission tables or ACLs beyond what is needed to answer (ideally none).
- Audit-log internals such as hashes or signatures.

## 4. Handling denied access

Built this way (app/pipeline/query.py; INV-1, INV-5):
- Filter silently at retrieval time; the answer is built only from allowed items.
- If nothing allowed remains, respond as "no relevant information found for
  you", not "access denied to <title>".
- Log the denial with the reason in the audit trail, where the compliance
  persona can see it. The asker does not see it.

## 5. Reporting a security issue during the hackathon

Tell the team immediately in the team channel and open an issue labelled
`security`. Do not push a fix that changes security behaviour without a review
from a second team member (see [CONTRIBUTING.md](../CONTRIBUTING.md) §4).

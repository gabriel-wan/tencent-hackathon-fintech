# docs/architecture/

Detailed architecture material that is too long for the top-level
[ARCHITECTURE.md](../../ARCHITECTURE.md), which remains the entry point.

Expected contents once the design is agreed (none exist yet):

- `trust-boundary.md` - the trust-boundary diagram the hackathon submission
  explicitly asks for (handbook, FinTech track, "The Solution Should Include").
- `permission-model.md` - how each platform's permission semantics are
  represented and evaluated (Confluence space/page, Jira project/role/issue,
  Slack channel membership, Google Drive file/folder/user).
- `audit-log.md` - the audit event schema and the tamper-evidence mechanism.
- `data-flow.md` - ingestion, freshness window, and the query path.

Keep every diagram consistent with the security boundary in ARCHITECTURE.md:
unauthorized content must never appear on the LLM side of the boundary.

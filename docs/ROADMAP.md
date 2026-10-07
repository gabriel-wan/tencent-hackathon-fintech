Status as of 8 October 2026: **Done**, **In progress** or **Not started**, with the pull request.

## 3 - 4 October
- **Task 1:** Set up the Jira, Confluence, Google Drive and Slack connectors and sync their data and permissions into the database. **Done** (#4)
- **Task 2:** Implement the frontend UI/UX (login, persona switcher, chat with answers and citations). **Done** (#6, open)
- **Task 3:** Set up the database schema, auth and permission filter, and the query pipeline (search → permission check → LLM answer). **Done** (#5)

## 5 - 6 October
- **Task 1:** Handle live permission changes and data freshness. **Done** (#10)
- **Task 2:** Build the compliance/audit dashboard. **In progress**: the page exists with mock data; the audit API it needs is in #11
- **Task 3:** Build the tamper-evident audit log and audit search API. **Done** (#11, open)

## 7 - 8 October
- **Task 1:** Build the PII redaction (Need-to-Know Shield). **Not started**
- **Task 2:** Polish the UI/UX and show redaction and freshness in the UI. **Not started** (the API already returns each citation's `synced_at`)
- **Task 3:** Build prompt injection protection and pass all 5 scenarios. **In progress**: retrieved text is already fenced as untrusted and citations are checked; no dedicated injection tests or scenario run yet

## 9 - 10 October
- **Task 1:** Deploy to Tencent Cloud (live link). **Not started**
- **Task 2:** Record the demo video and make the cover image. **Not started**
- **Task 3:** Write tests, fix bugs and update the docs. **In progress** (ongoing with each pull request)

## 11 - 12 October
- **Task 1:** Final testing on a clean machine. **Not started**
- **Task 2:** Write the project description and diagrams. **Not started**
- **Task 3:** Collect the CodeBuddy/WorkBuddy screenshots and submit. **Not started**: the evidence log is still empty, and without proof the project is not scored

13 - 16 October: buffer

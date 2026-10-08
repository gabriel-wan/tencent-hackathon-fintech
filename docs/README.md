# KnowBuddy docs

**For:** anyone looking for something in the docs.
**You'll:** find the one page that answers your question, and what our terms mean.

## I want to…

| … | Read |
|---|---|
| run KnowBuddy on my computer and try it | [RUNNING.md](RUNNING.md) |
| test a change, or check everything before submitting | [TESTING.md](TESTING.md) |
| see how it's built | [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) (what is built right now: [architecture/CURRENT.md](architecture/CURRENT.md)) |
| know the security rules and what guards them | [SECURITY.md](SECURITY.md) |
| connect Google Drive, Slack, Jira or Confluence, or deploy them for real | [connectors/GUIDE.md](connectors/GUIDE.md) |
| know the project's goals, scope and progress | [PROJECT.md](PROJECT.md) |
| know why something was decided | [decisions/DECISIONS.md](decisions/DECISIONS.md) |
| change code, open a pull request, or propose a decision | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| check what the hackathon requires | [hackathon/requirements.md](hackathon/requirements.md), [hackathon/submission.md](hackathon/submission.md) |

## Where things are

```
README.md            what KnowBuddy is, in one page
CONTRIBUTING.md      how the team works and decides
AGENTS.md            rules for AI coding agents (CLAUDE.md points to it)
.github/             the pull request template
docs/
├── README.md        this map
├── RUNNING.md       run and use it
├── TESTING.md       test it
├── SECURITY.md      threat model and security invariants
├── PROJECT.md       goals, users, scenarios, scope, roadmap and status
├── architecture/    how it's built: overview, what's built now, query pipeline, connectors
├── connectors/      per-tool setup (GUIDE.md) and API research for each tool
├── decisions/       the decision log (DECISIONS.md) and the ADR template
└── hackathon/       the challenge, requirements, submission checklist, tool-usage evidence
backend/             FastAPI app: app/ (code), tests/, migrations/
frontend/            Next.js app (its README covers frontend conventions)
scripts/             helper scripts (check_doc_links.py)
docker-compose.yml   runs db, migrate, backend, sync and frontend
```

## Glossary

| Term | Meaning |
|---|---|
| **Company** | One organisation using KnowBuddy. It starts when the first full member of a new Slack workspace connects Slack; many companies share one deployment and never see each other's data |
| **Admin** | The person who chooses the boundary and triggers syncs, and who reads the audit log (one role, ADR-007). A company's first full Slack member |
| **Connection** | A person's stored, encrypted sign-in to one tool (Google, Slack or Atlassian). Connecting a tool is also how you sign in: there is no password |
| **Principal** | One identity a person has in a tool, written like `slack:user:U024`, `slack:members` or `google:domain:co.com` |
| **ACL** | Access control list: the principals allowed to read a document, copied from the tool. It may list extra people, never fewer |
| **Boundary** | The channels, folders, projects and spaces the admin lets KnowBuddy read. Anything outside it is never used, even for people who can see it in the tool |
| **Scope** | One item in the boundary, such as one Slack channel or one Drive folder |
| **Sync** | Copying everything inside the boundary, with its ACLs, into KnowBuddy's database: every 5 minutes, or at once with "sync now" |
| **Live check** | At question time, asking each tool, as the person asking, whether they can still read each candidate document. A "no", an error or a timeout drops it |
| **Citation** | A source listed under an answer, with when it was last synced |
| **Audit event** | One record of something that happened (a question, a boundary change, a search of the log). Records are chained by hash, so a change is detectable |
| **Restricted match** | A document a question matched but the asker may not see. Recorded in the audit log only, never shown to them |
| **Persona** | A fictional development user (Alice, Ben, Charlie, Priya, Dana) from the seed data |
| **Mock mode** | Fake chat answers for frontend work, labelled MOCK DATA, development only |
| **TokenHub** | Tencent Cloud's service that runs the LLM (`hy3`) and the embedding model |

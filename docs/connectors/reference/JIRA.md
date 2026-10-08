# Jira Connector

> **API research and reference** for this tool. What KnowBuddy's code does with it:
> [architecture/CONNECTORS.md](../../architecture/CONNECTORS.md). Setting up its sign-in: [SETUP.md](../SETUP.md).

## 1. Introduction

Jira holds tickets (bugs, incidents, customer support cases); since 2025
the UI calls projects "spaces" and issues "work items", but the API still
says `project` and `issue`. Our connector reads, through one person's own
Atlassian sign-in (shared with [Confluence](CONFLUENCE.md)), the **text** of
every ticket and **who can see it**: everyone with the space's "Browse
projects" permission. Ticket security levels are not stored yet; the live
check, asked as the user, trims those tickets. Security levels hide single
tickets (the security-team ticket), and support tickets are where customer data
gets pasted (the Need-to-Know Shield), so the live check has the final say.

## 2. Glossary

| Term | Meaning |
|---|---|
| Space | The UI name for a Jira project, called `project` in the API and JQL, e.g. `PAY`. |
| Work item | The UI name for a ticket, called `issue` in the API, with a numeric `id` (e.g. `10001`) and a `key` (e.g. `PAY-12`). |
| Company-managed space | A space whose permissions come from admin-defined schemes, and the **only** kind that can hide single tickets. |
| Team-managed space | A simple space (like the default "My Team") with fixed roles and no per-ticket security. |
| Permission scheme | The admin-defined rules for a company-managed space, e.g. who holds "Browse projects". |
| Browse projects | The permission (`BROWSE_PROJECTS`) that lets someone see a space's tickets at all. |
| Holder | Who a grant is given to: a group, a project role, a user, the reporter/assignee, or all Jira users. |
| Project role | A per-space label (e.g. Developers) whose members (users and groups) are set per space. |
| Group | A site-wide named list of people, e.g. `security-team`, shared with Confluence. |
| Issue security scheme | The set of security levels a space can use. |
| Issue security level | A named list of holders (e.g. "Security team") that, when set on a ticket, hides it from everyone else. |
| JQL | Jira Query Language for searching tickets, e.g. `project = PAY AND updated >= "2026/10/01 13:00"`. |
| ADF | Atlassian Document Format, the nested JSON that descriptions and comments are stored in. |
| accountId | The permanent ID of an Atlassian user, shared with Confluence and used instead of email (which is often hidden). |
| nextPageToken | Cursor in search results: send it back to get the next page until it's missing. |
| Principal | A namespaced ID stored in ACLs, e.g. `atlassian:user:<accountId>` or `public`. |
| ACL | The list of principals stored on a ticket, any one of which lets search include it (the live check has the final say). |
| Sidebar "Projects" | A separate Atlassian app (goals and status updates), **not** Jira projects, so ignore it. |
| Free plan | Jira's free tier, which can't edit permissions or security levels, so it can't be used. |

## 3. Identity Access Management and Permissions

Hiding single tickets needs a **company-managed** space.

```
Site
└── Space PAY        Browse projects → role Developers, group support
    ├── PAY-12  security: none            → Developers + support
    └── PAY-13  security: "Security team" → Developers + support, AND group security-team
        └── comments, attachments         → same as the ticket
```

- Grants and security levels are given to **holders**: groups, project roles, users, reporter/assignee, or all Jira users.
- A ticket has **at most one** security level.

**Rule:** you can see a ticket if you hold "Browse projects" on its space
**and** (it has no security level **or** you are in that level). We store the
narrower of the two as the ACL (Section 5), and Jira itself (4.9) has the final say.

## 4. APIs available

| API / tool | What it gives | Use? |
|---|---|---|
| **REST API v3** (`/rest/api/3`) | Tickets, schemes, roles, groups, permission checks | **Yes** |
| **`httpx`** | Plain HTTP calls with Basic auth (same client as Confluence) | **Yes** |
| Webhooks | Push on ticket change | No: need a public URL. JQL polling is enough |
| Official Atlassian (Rovo) MCP server `mcp.atlassian.com` | Lets an AI agent use Jira **as one signed-in user** | No: can't tell us what *other* users can see |

### Auth / setup

```
1. A plan with permissions: Standard (or the developer site go.atlassian.com/cloud-dev)   ← Free can't do this
2. Create space → template → "Company-managed"                          ← not the default "My Team"
3. Settings ⚙ → Work items → Issue security schemes → add levels → associate with the space
```

Every call uses one person's own Atlassian sign-in, shared with Confluence: the company admin's
for sync, the asking user's for the live check (`store.client(engine, user_id, "jira")`).

Built today: the ACL is everyone with **Browse projects**, from
`GET /rest/api/3/user/permission/search?permissions=BROWSE_PROJECTS&projectKey=…` (Jira expands
groups and roles itself), so issue security levels (4.5, 4.6) are not applied; the live check (4.9,
as the user, one call) trims those. `source_id` is the numeric issue ID, which 4.9 takes.

### 4.1 Tickets changed since the checkpoint

| | |
|---|---|
| Request | `POST /rest/api/3/search/jql` |
| Body | `{ "jql": "project in (PAY) AND updated >= \"2026/10/01 13:00\" ORDER BY updated ASC", "fields": ["summary","description","comment","security","updated","project","reporter","assignee"], "maxResults": 100 }` |

```json
{
  "issues": [{
    "id": "10013", "key": "PAY-13",
    "fields": {
      "summary": "Customer double-charged",
      "description": { "type": "doc", "content": [ { "type": "paragraph", "content": [ { "type": "text", "text": "Card ending 4242 was charged twice." } ] } ] },
      "comment": { "comments": [ { "body": { "type": "doc", "content": [ ... ] } } ], "total": 1 },
      "security": { "id": "10100", "name": "Security team" },
      "project": { "id": "10000", "key": "PAY" },
      "reporter": { "accountId": "5b10-ben" }, "assignee": { "accountId": "5b10-sara" },
      "updated": "2026-10-01T09:00:00.000+0800"
    }
  }],
  "nextPageToken": "..."
}
```
Notes: resend the body with `"nextPageToken"` until it's missing. `security` is `null` when unrestricted. Changing a ticket's security level also bumps `updated`, so this catches it.

### 4.2 All ticket keys (delete reconcile)

| | |
|---|---|
| Request | `POST /rest/api/3/search/jql` with `{ "jql": "project in (PAY)", "fields": ["key"], "maxResults": 1000 }` |

Response: `{ "issues": [{ "id": "10013", "key": "PAY-13" }], "nextPageToken": "..." }`

### 4.3 All comments of a ticket

| | |
|---|---|
| Request | `GET /rest/api/3/issue/{key}/comment?startAt=0&maxResults=100` |

Notes: needed only when `comment.total` in 4.1 is larger than the comments returned.

### 4.4 Who can browse a space

| | |
|---|---|
| Request | `GET /rest/api/3/project/{key}/permissionscheme?expand=permissions` |

```json
{ "id": 10000, "permissions": [
  { "permission": "BROWSE_PROJECTS", "holder": { "type": "projectRole", "value": "10002" } },
  { "permission": "BROWSE_PROJECTS", "holder": { "type": "group", "value": "g-support" } }
] }
```
Notes: keep only `BROWSE_PROJECTS`. Map each holder per the table in Section 5.

### 4.5 The space's issue security scheme

| | |
|---|---|
| Request | `GET /rest/api/3/project/{key}/issuesecuritylevelscheme` |

Response: `{ "id": 10000, "name": "PAY security" }`

### 4.6 Members of a security level

| | |
|---|---|
| Request | `GET /rest/api/3/issuesecurityschemes/{schemeId}/members?issueSecurityLevelId=10100` |

```json
{ "values": [{ "issueSecurityLevelId": 10100, "holder": { "type": "group", "value": "g-security" } }], "isLast": true }
```

### 4.7 Members of a project role

| | |
|---|---|
| Request | `GET /rest/api/3/project/{key}/role` (list), then `GET /rest/api/3/project/{key}/role/{roleId}` |

```json
{ "id": 10002, "name": "Developers", "actors": [
  { "type": "atlassian-user-role-actor",  "actorUser":  { "accountId": "5b10-alice" } },
  { "type": "atlassian-group-role-actor", "actorGroup": { "groupId": "g-dev", "name": "jira-developers" } }
] }
```

### 4.8 Group members

| | |
|---|---|
| Request | `GET /rest/api/3/group/member?groupId=g-security&maxResults=50` |

Response: `{ "values": [{ "accountId": "5b10-sara" }], "isLast": true }`. Shared with Confluence.

### 4.9 Which of these tickets can user X see? (live gate)

| | |
|---|---|
| Request | `POST /rest/api/3/permissions/check` |
| Body | `{ "accountId": "<id>", "projectPermissions": [{ "permissions": ["BROWSE_PROJECTS"], "issues": [10012, 10013] }] }` |

```json
{ "projectPermissions": [{ "permission": "BROWSE_PROJECTS", "issues": [10012], "projects": [] }] }
```
Notes: lists only the tickets the user can see. One call covers all tickets in the final context.

## 5. Output Schema Contract

One document per ticket:

```jsonc
{
  "source": "jira",
  "source_id": "10013",                                           // issue.id (the live check, 4.9, takes IDs)
  "title": "PAY-13: Customer double-charged",                     // key + summary
  "text": "Card ending 4242 was charged twice. Refund issued.",   // description + comments, ADF flattened
  "url": "https://yourteam.atlassian.net/browse/PAY-13",          // site + /browse/ + key
  "updated_at": "2026-10-01T01:00:00Z",                           // fields.updated, in UTC
  "metadata": { "assignee": "atlassian:user:5b10-sara" },         // used by the Need-to-Know Shield
  "acl": ["atlassian:user:5b10-sara"]                             // security-level holders, expanded
}
```

`acl` = the security level's holders (4.6) if a level is set, otherwise the
"Browse projects" holders (4.4), expanded into users:

| Holder `type` (4.4 / 4.6) | Becomes |
|---|---|
| `user` | `atlassian:user:<value>` |
| `group` | its members (4.8) |
| `projectRole` | its actors (4.7), with groups expanded via 4.8 |
| `reporter` / `assignee` / `projectLead` | that person's `atlassian:user:<accountId>` (per ticket) |
| `applicationRole` (all Jira users) / `anyone` | `public` |

## 6. Summary

**Takeaways**

- **Free plan can't hide tickets**, and **team-managed spaces can't either**. Use a paid plan and a company-managed space.
- UI says space / work item. **Code says `project` / `issue`.**
- Built ACL = "Browse projects" holders (security levels not applied; the live check trims). The fuller design: security-level holders, with reporter/assignee holders as per-ticket users.
- A security-level change bumps `updated`, so `sync` catches it. Scheme and role changes are caught by `sweep`.
- Always send `fields`. Descriptions and comments are ADF JSON, so flatten them by joining every `"text"`.
- People are `accountId`s. Emails are usually `null`.

**How this connector implements the contract** ([architecture](../../architecture/CONNECTORS.md)). Built today (`app/sync.py`, `jira.py`): every 5 minutes, 4.1 over each boundary project in full, with the project's ACL from the users who can browse it (issue security levels not applied: too wide, trimmed by the live check), and `can_read` (4.9) as the user. The table is the cursor-based design for when projects outgrow that.

| Method | Calls | Runs |
|---|---|---|
| `sync(cursor)` | 4.1 JQL `updated >= cursor` (+ 4.3 if comments are truncated) → ACL (4.4–4.8). New cursor = latest `updated` seen | every 5 min |
| `sweep()` | 4.2 for every key → ACL per ticket (schemes, levels, roles and groups cached per run) | every 30 min |
| `can_read(principal, ids)` | 4.9, one call with all ticket IDs | each question, final context only |

One module: `backend/app/connectors/jira.py`, sharing the `httpx` client with Confluence.

**Day-1 checks**

1. A ticket with a security level: 4.9 leaves it out for a non-member.
2. Holder fields (`type`, `value`) in 4.4 and 4.6 match the examples on your site.
3. The `Issue security schemes` menu path exists (Atlassian moves menus).

## 7. Sources

- [Jira Free permission limits](https://support.atlassian.com/jira-cloud-administration/docs/permissions-and-issue-level-security-in-free-plans/)
- [Team-managed space permissions](https://support.atlassian.com/jira-software-cloud/docs/next-gen-permissions/)
- [Projects renamed to spaces](https://community.atlassian.com/forums/Jira-articles/More-on-the-move-from-Jira-Projects-to-Spaces/ba-p/3085938)
- [Jira search (JQL) API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/)
- [Jira issue security schemes API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-security-schemes/)
- [Jira project role actors API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-project-role-actors/)
- [Jira permissions API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-permissions/)
- [Atlassian email visibility](https://developer.atlassian.com/cloud/jira/platform/profile-visibility/)
- [Atlassian Rovo MCP server](https://github.com/atlassian/atlassian-mcp-server)

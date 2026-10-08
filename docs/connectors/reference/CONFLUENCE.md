# Confluence Connector

> **API research and reference** for this tool. What KnowBuddy's code does with it:
> [architecture/CONNECTORS.md](../../architecture/CONNECTORS.md). Setting up its sign-in: [SETUP.md](../SETUP.md).

## 1. Introduction

Confluence is Atlassian's wiki: pages (runbooks, design docs, incident
reports) live inside spaces, and it shares one site and sign-in with
[Jira](JIRA.md). Our connector reads, through one person's own Atlassian
sign-in (the admin's for sync), the **text** of every page and **who can read
it** (page read restrictions, including inherited ones; space permissions are
not stored yet). Those rules are the "security-team-only page" case (challenge
scenario 3), so the live check, a search asked as the user, has the final say.

## 2. Glossary

| Term | Meaning |
|---|---|
| Site | Your Atlassian instance, e.g. `https://yourteam.atlassian.net`, shared by Confluence and Jira. |
| Space | A top-level container of pages with its own permissions, identified by an `id` and a short `key` like `ENG`. |
| Page | One wiki document, identified by a numeric `id` like `98765`. |
| Ancestor | Any page above a page in the tree (parent, grandparent, ...), whose restrictions also apply. |
| Space permission | The setting that decides who can open a space at all. |
| Page restriction | An optional extra lock that limits a page (and everything below it) to named users or groups. |
| Group | A site-wide named list of people, e.g. `security-team`, shared by Confluence and Jira. |
| accountId | The opaque, permanent ID of an Atlassian user (e.g. `5b10ac8d82e05b22cc7d4ef5`), shared by Confluence and Jira. |
| API token | A password-like secret from id.atlassian.com. **Not used**: every call is one person's OAuth sign-in. |
| Storage format | The HTML-like markup Confluence stores page bodies in, e.g. `<p>Step 1</p>`. |
| CQL | Confluence Query Language, used here to find pages changed since a time. |
| Cursor | The `_links.next` URL in a response, which you call to get the next page of results. |
| Checkpoint | The last-modified time we synced up to, stored in `sync_state`. |
| Principal | A namespaced ID our system stores in ACLs: `atlassian:user:<accountId>`. Groups are expanded into their users (4.8), as in Jira. |
| ACL | The list of principals stored on a page, any one of which lets search include it (the live check has the final say). |
| Free plan | Confluence's free tier, which has **no permissions** (every user sees everything), so it can't be used. |

## 3. Identity Access Management and Permissions

```
Site (yourteam.atlassian.net)
├── Space ENG          space permission: group all-staff
│   ├── Page "Failover runbook"      → all-staff
│   └── Page "Vendor contract"       → restricted: sara, group legal
│       └── Child page "Pricing"     → restricted: sara        (and its parent's restriction applies too)
└── Space SECURITY     space permission: group security-team
    └── Page "Q3 breach report"      → security-team
```

- Space permissions and page restrictions are granted to **users** or **groups**.
- Every restriction on a page **and on each of its ancestors** applies at the same time.
- Site admins are **not** automatically able to read restricted pages.

**Rule:** you can read a page if you pass the space permission **and** every
restriction on the page and its ancestors. We store the narrowest of those
layers as the ACL (Section 5), and Confluence itself (4.9) has the final say.

## 4. APIs available

| API / tool | What it gives | Use? |
|---|---|---|
| **REST API v2** (`/wiki/api/v2`) | Spaces, pages, bodies, ancestors, space permissions | **Yes** |
| **REST API v1** (`/wiki/rest/api`) | CQL search, page restrictions, group members, permission check | **Yes** |
| **`httpx`** (Python HTTP client) | Plain HTTP calls with Basic auth | **Yes**, no SDK needed |
| `atlassian-python-api` | Community wrapper | No: unneeded dependency |
| Webhooks | Push on page change | No: need a Forge/Connect app. CQL polling is enough |
| Official Atlassian (Rovo) MCP server `mcp.atlassian.com` | Lets an AI agent use Confluence **as one signed-in user** | No: can't tell us what *other* users can see |

### Auth / setup

A plan with permissions is needed to restrict pages: Standard, or the developer site
go.atlassian.com/cloud-dev (Free won't work). Every call uses one person's own Atlassian
sign-in ([SETUP.md §5](../SETUP.md#5-jira-and-confluence)), shared with Jira: the company admin's
for sync, the asking user's for the live check. There is no API token. Sync sees what the admin
sees, so the admin must be able to open every space added to the boundary.

```python
from app.connectors import atlassian, store
with store.client(engine, user_id, "confluence") as http:   # httpx.Client via api.atlassian.com
    atlassian.request("GET", "/wiki/api/v2/spaces", http=http)
```

Built today: unrestricted pages get `public` (the whole company) instead of the space's read
principals (4.6); the live check, a CQL search as the user, trims anyone extra.

### 4.1 List spaces

| | |
|---|---|
| Request | `GET /wiki/api/v2/spaces?limit=250` |

```json
{ "results": [{ "id": "123", "key": "ENG", "name": "Engineering" }], "_links": { "next": "..." } }
```

### 4.2 List page IDs in a space (delete reconcile)

| | |
|---|---|
| Request | `GET /wiki/api/v2/spaces/{spaceId}/pages?limit=250` |

```json
{ "results": [{ "id": "98765", "title": "Failover runbook", "parentId": "55555" }], "_links": { "next": "/wiki/api/v2/spaces/123/pages?cursor=..." } }
```
Notes: follow `_links.next` until it's missing. Delete only after the full list is read.

### 4.3 Pages changed since the checkpoint

| | |
|---|---|
| Request | `GET /wiki/rest/api/search?cql=type=page and lastmodified >= "2026/10/01 13:00"&limit=100` |

```json
{ "results": [{ "content": { "id": "98765", "title": "Failover runbook" }, "lastModified": "2026-10-01T13:05:00.000Z" }], "_links": { "next": "..." } }
```
Notes: CQL dates use `yyyy/MM/dd HH:mm`. Restriction changes do **not** update `lastmodified`, which is why permission sync is a separate job.

### 4.4 One page with its body

| | |
|---|---|
| Request | `GET /wiki/api/v2/pages/{id}?body-format=storage` |

```json
{
  "id": "98765", "title": "Failover runbook", "spaceId": "123",
  "version": { "number": 3, "createdAt": "2026-10-01T13:05:00.000Z" },
  "body": { "storage": { "value": "<p>Step 1: <strong>fail over</strong> the DB.</p>" } },
  "_links": { "webui": "/spaces/ENG/pages/98765/Failover+runbook", "base": "https://yourteam.atlassian.net/wiki" }
}
```

### 4.5 Ancestors of a page

| | |
|---|---|
| Request | `GET /wiki/api/v2/pages/{id}/ancestors` |

```json
{ "results": [{ "id": "55555", "type": "page" }] }
```

### 4.6 Space permissions (who can open the space)

| | |
|---|---|
| Request | `GET /wiki/api/v2/spaces/{spaceId}/permissions` |

```json
{ "results": [{ "principal": { "type": "group", "id": "g-all-staff" }, "operation": { "key": "read", "targetType": "space" } }] }
```
Notes: keep only `operation.key = "read"` with `targetType = "space"`. `principal.type` is `user` or `group`. A `role` type (space roles) must be expanded via the Space Roles API.

### 4.7 Read restrictions on a page

| | |
|---|---|
| Request | `GET /wiki/rest/api/content/{id}/restriction/byOperation/read?expand=restrictions.user,restrictions.group` |

```json
{ "operation": "read", "restrictions": {
  "user":  { "results": [{ "accountId": "5b10-sara" }] },
  "group": { "results": [{ "id": "g-legal", "name": "legal" }] } } }
```
Notes: both lists empty means the page itself is unrestricted. Check each ancestor (4.5) too.

### 4.8 Group members

| | |
|---|---|
| Request | `GET /wiki/rest/api/group/{groupId}/membersByGroupId?limit=200` |

```json
{ "results": [{ "accountId": "5b10-sara", "accountType": "atlassian" }], "size": 1 }
```
Notes: used to expand groups into users in the ACL. Cache per run and share with Jira.

### 4.9 Can user X read page Y? (live gate)

| | |
|---|---|
| Request | `POST /wiki/rest/api/content/{pageId}/permission/check` |
| Body | `{ "subject": { "type": "user", "identifier": "<accountId>" }, "operation": "read" }` |

```json
{ "hasPermission": false, "errors": [] }
```
Notes: Confluence's own answer, including space permissions, restrictions and inheritance. Used only on the final context of an answer.

## 5. Output Schema Contract

One document per page:

```jsonc
{
  "source": "confluence",
  "source_id": "77777",                                           // page.id ("Pricing")
  "title": "Pricing",                                             // page.title
  "text": "Discount bands for 2027 ...",                          // body.storage.value, tags stripped
  "url": "https://yourteam.atlassian.net/wiki/spaces/ENG/pages/77777/Pricing", // _links.base + webui
  "updated_at": "2026-10-01T13:05:00Z",                           // version.createdAt
  "acl": ["atlassian:user:5b10-sara"]
}
```

`acl` = the users of the **deepest** read restriction on the page or its
ancestors (4.5 + 4.7), with groups expanded via 4.8. If nothing is restricted,
use the space's read principals (4.6). The true readers are always inside it,
so search never misses them, and 4.9 removes anyone extra.

## 6. Summary

**Takeaways**

- **Free plan has no permissions.** A plan with permissions is required.
- Sync uses the **admin's** sign-in, so the admin must be able to open every restricted page, or it's invisible to the connector.
- **Check ancestors.** A restriction on any page above applies too. The live check (4.9) is the authority either way.
- Restriction changes don't bump `lastmodified`, so `sweep` recomputes every ACL.
- Page bodies are HTML. Strip the tags.
- People are `accountId`s. Identity linking uses the signed-in person's own verified email (`api.atlassian.com/me`).

**How this connector implements the contract** ([architecture](../../architecture/CONNECTORS.md)). Built today (`app/sync.py`, `confluence.py`): every 5 minutes, the space's pages (v2, with bodies and parents) in full, the deepest read restriction per page (groups expanded, cached per run; space permissions not applied: too wide, trimmed by the live check), and `can_read` as one CQL search `id in (...)` as the user. The table is the cursor-based design for when spaces outgrow that.

| Method | Calls | Runs |
|---|---|---|
| `sync(cursor)` | 4.3 CQL since cursor → 4.4 per page → ACL (4.5–4.8). New cursor = latest `lastModified` seen | every 5 min |
| `sweep()` | 4.1 → 4.2 every space → ACL per page (space permissions, restrictions and groups cached per run) | every 30 min |
| `can_read(principal, ids)` | 4.9 per page, with the user's `accountId` | each question, final context only |

One module: `backend/app/connectors/confluence.py`.

**Day-1 checks**

1. 4.9 returns `false` for a non-member on a page whose **ancestor** is restricted.
2. 4.6's response shape (principal types, `operation` fields) matches the example on your site.
3. The admin token can call 4.7, 4.8 and 4.9 for other users (no 403).

## 7. Sources

- [Confluence Free has no permissions](https://support.atlassian.com/confluence-cloud/docs/manage-permissions-in-the-free-edition-of-confluence-cloud/)
- [Confluence permissions structure](https://support.atlassian.com/confluence-cloud/docs/what-are-confluence-cloud-permissions-and-restrictions/)
- [Confluence REST API v2 (pages, ancestors)](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/)
- [Confluence space permissions API (v2)](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-space-permissions/)
- [Confluence content restrictions API (v1)](https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content-restrictions/)
- [Confluence permission check API (v1)](https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content-permissions/)
- [Atlassian email visibility](https://developer.atlassian.com/cloud/jira/platform/profile-visibility/)
- [Atlassian Rovo MCP server](https://github.com/atlassian/atlassian-mcp-server)

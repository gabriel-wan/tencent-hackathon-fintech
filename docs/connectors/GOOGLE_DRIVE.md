# Google Drive Connector

## 1. Introduction

Google Drive stores files (Google Docs, Sheets, Slides, PDFs) in folders and
shared drives, and each file can be shared with people, groups, a whole
domain, or "anyone with the link". Our connector reads every changed file's
**text** and its **full sharing list**, and follows Drive's **change feed**, so
edits, re-shares and lost access all arrive on the next sync. Sharing is set
per file and per folder, and "anyone with the link" is the clearest example of
oversharing, so the sharing list is stored exactly and the overshared case is
flagged.

## 2. Glossary

| Term | Meaning |
|---|---|
| File | Any item in Drive, identified by a `fileId` like `1AbC...`. |
| Folder | A file with `mimeType = application/vnd.google-apps.folder` that contains other files. |
| mimeType | The file's type, e.g. `application/vnd.google-apps.document` (Google Doc) or `application/pdf`. |
| Google-native file | A Doc, Sheet or Slides file that has no raw bytes and must be **exported** to get text. |
| Binary file | An uploaded file (PDF, image, .docx) that is **downloaded** as raw bytes. |
| My Drive | Each account's personal storage. |
| Shared drive | Team-owned storage (Google Workspace) whose members get access to everything inside. |
| Permission | One sharing entry on a file: who gets access and at what level. |
| Role | The access level of a permission: `owner`, `organizer`, `fileOrganizer`, `writer`, `commenter` or `reader`. Any role can read. |
| Type | Who the permission is for: `user`, `group`, `domain` or `anyone`. |
| Anyone with the link | A permission with `type: anyone`, meaning anyone holding the URL can open the file. |
| Inherited permission | Access a file gets from its folder or shared drive, already listed on the file. |
| Service account | A robot Google account our worker uses in Workspace mode. |
| Domain-wide delegation | Workspace admin setting that lets the service account read Drive **as any user** in the domain. |
| Directory API | The Workspace Admin SDK API that lists group members. |
| OAuth client | The app identity created in Google Cloud Console for personal-account mode. |
| Testing mode | Default state of a new OAuth app, in which refresh tokens **expire after 7 days**. |
| `fields` mask | Query parameter listing exactly which fields to return; without it you get almost nothing. |
| pageToken / nextPageToken | Cursor for paging: send back `nextPageToken` as `pageToken` until it's missing. |
| Change feed | Drive's list of every file edited, re-shared, deleted or made inaccessible since a stored `pageToken`. |
| webViewLink | The browser URL of a file, used for citations. |
| Principal | A namespaced ID stored in ACLs, e.g. `google:user:<email>`, `google:domain:<domain>`, `public`. |

## 3. Identity Access Management and Permissions

```
Domain company.com
├── Shared drive "Finance"   members: group finance@company.com
│   └── File "Q3 budget"        → finance group (inherited)
└── My Drive (alice@company.com)
    └── Folder "Ops"            shared with: ben (reader)
        ├── File "Runbook"      → alice (owner), ben (inherited)
        └── File "Pricing"      → anyone with the link   ⚠ overshared
```

- Each file has a **permission list** of `type` (`user`, `group`, `domain`, `anyone`) + `role`. For us, any role means "can read".
- Folder and shared-drive access **already appears** on each file's list, so you never walk the tree.

**Rule:** you can read a file if your email, one of your groups, or your
domain is on its list, or the list has `anyone`.

## 4. APIs available

| API / tool | What it gives | Use? |
|---|---|---|
| **Drive REST API v3** | Files, content, permissions, change feed | **Yes** |
| **Admin SDK Directory API** | Members of Google Groups (Workspace) | **Yes**, for `group` permissions |
| **`google-api-python-client`** + `google-auth` | Ready-made calls, service account and OAuth auth | **Yes** |
| Push notifications (`changes.watch`) | Google calls our URL on change | No: needs a public HTTPS URL. Polling the change feed is enough |
| Docs / Sheets APIs | Rich structure (tables, styles) | No: export gives us the text |
| Official Drive MCP server `drivemcp.googleapis.com` | Lets an AI agent use Drive **as one signed-in user** | No: can't tell us what *other* users can see |

### Auth / setup

**Workspace (production):**
```
1. Google Cloud project → enable Drive API + Admin SDK API → create a service account → JSON key
2. Workspace Admin console → Security → API controls → Domain-wide delegation → add the service account's client ID with scopes:
   https://www.googleapis.com/auth/drive.readonly
   https://www.googleapis.com/auth/admin.directory.group.member.readonly
3. backend/.env: GOOGLE_SERVICE_ACCOUNT_JSON (key file contents, one line, single-quoted),
   GOOGLE_ADMIN_EMAIL (the admin to impersonate for Directory calls)
```

**Personal accounts (development):** used when `GOOGLE_SERVICE_ACCOUNT_JSON` is unset.
```
1. Google Cloud project → enable Drive API → OAuth consent screen → Publish app   ← Testing mode tokens expire after 7 days
2. Credentials → OAuth client ID → type "Web application" → redirect URI https://developers.google.com/oauthplayground
3. developers.google.com/oauthplayground → ⚙ → "Use your own OAuth credentials" → paste ID + secret
   → scope https://www.googleapis.com/auth/drive.readonly → Authorize → Exchange code for tokens
4. backend/.env: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
```

Check either mode with `python -m app.connectors drive` (see `backend/README.md`).

```python
from google.oauth2 import service_account
from googleapiclient.discovery import build
creds = service_account.Credentials.from_service_account_file(KEY_FILE, scopes=[DRIVE_RO])
drive_as = lambda email: build("drive", "v3", credentials=creds.with_subject(email))  # act as a user
```

Base URL for all Drive calls: `https://www.googleapis.com/drive/v3`. For
shared drives, add `supportsAllDrives=true&includeItemsFromAllDrives=true`.

### 4.1 `files.list`: list files with sharing (initial load, delete reconcile)

| | |
|---|---|
| Request | `GET /files?q=trashed=false&fields=nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,permissions(type,role,emailAddress,domain))&pageSize=100` |

```json
{
  "files": [{ "id": "1AbC", "name": "Q3 budget", "mimeType": "application/vnd.google-apps.document",
              "modifiedTime": "2026-10-01T05:00:00.000Z", "webViewLink": "https://docs.google.com/document/d/1AbC/edit",
              "permissions": [{ "type": "group", "role": "reader", "emailAddress": "finance@company.com" }] }],
  "nextPageToken": "~!!~AI9..."
}
```
Notes: put `nextPageToken` in the `fields` mask, or paging silently stops after page 1.

### 4.2 `changes.getStartPageToken` + `changes.list`: what changed since the checkpoint

| | |
|---|---|
| 1. Bookmark "now" (once) | `GET /changes/startPageToken` → `{ "startPageToken": "1234" }` |
| 2. Every run | `GET /changes?pageToken=1234&includeRemoved=true&fields=nextPageToken,newStartPageToken,changes(fileId,removed,file(name,mimeType,modifiedTime,trashed,webViewLink,permissions(type,role,emailAddress,domain)))` |

```json
{
  "changes": [
    { "fileId": "1AbC", "removed": false, "file": { "name": "Q3 budget", "modifiedTime": "2026-10-02T03:00:00.000Z", "trashed": false, "permissions": [ ... ] } },
    { "fileId": "9XyZ", "removed": true }
  ],
  "newStartPageToken": "1240"
}
```
Notes: follow `nextPageToken`. The response with `newStartPageToken` ends the
run, and that token is the new cursor. `removed: true` means deleted **or no
longer accessible**. Sharing changes appear as normal changes with the new
`permissions`.

### 4.3 `files.export`: text from a Google Doc or Sheet

| | |
|---|---|
| Request | `GET /files/{fileId}/export?mimeType=text/plain` (Docs) or `text/csv` (Sheets, first sheet) |

Response: the content as plain text. Notes: Google-native files only, capped at 10 MB.

### 4.4 `files.get?alt=media`: download a binary file

| | |
|---|---|
| Request | `GET /files/{fileId}?alt=media` |

Response: raw bytes (e.g. a PDF). Extract the text yourself (e.g. `pypdf`).

### 4.5 `permissions.list`: full sharing list of one file

| | |
|---|---|
| Request | `GET /files/{fileId}/permissions?fields=permissions(type,role,emailAddress,domain)` |

```json
{ "permissions": [
  { "type": "user",   "role": "owner",  "emailAddress": "alice@company.com" },
  { "type": "domain", "role": "reader", "domain": "company.com" },
  { "type": "anyone", "role": "reader" }
] }
```
Notes: use when the embedded `permissions` in 4.1/4.2 are missing or truncated.

### 4.6 `files.get` as a specific user (live gate)

| | |
|---|---|
| Request | `GET /files/{fileId}?fields=id`, authenticated **as that user**: their own OAuth sign-in (ADR-002), or `creds.with_subject(email)` in Workspace mode |

Response: `200` = the user can read it, `404` = they can't. Notes: Google's
own answer. Up to 100 checks go in one batch request (`POST /batch/drive/v3`).
Implemented as `drive.can_read(credentials, file_ids)`.

### 4.7 Directory API: group members

| | |
|---|---|
| Request | `GET https://admin.googleapis.com/admin/directory/v1/groups/{groupEmail}/members?includeDerivedMembership=true` |

```json
{ "members": [{ "email": "sara@company.com", "type": "USER", "status": "ACTIVE" }], "nextPageToken": "..." }
```
Notes: `includeDerivedMembership=true` flattens nested groups.

## 5. Output Schema Contract

One document per file:

```jsonc
{
  "source": "drive",
  "source_id": "1AbC",                                   // file.id
  "title": "Q3 budget",                                  // file.name
  "text": "Revenue target for Q3 is ...",                // export (4.3) or download (4.4)
  "url": "https://docs.google.com/document/d/1AbC/edit", // file.webViewLink
  "updated_at": "2026-10-01T05:00:00Z",                  // file.modifiedTime
  "metadata": { "overshared": true },                    // any type: anyone
  "acl": ["google:user:sara@company.com", "google:user:alice@company.com", "public"]
}
```

| Permission `type` | Becomes |
|---|---|
| `user` | `google:user:<emailAddress>` |
| `group` | its members (4.7), as `google:user:<email>` |
| `domain` | `google:domain:<domain>` (held by every user whose verified email is on that domain) |
| `anyone` | `public`, and set `metadata.overshared = true` |

## 6. Summary

**Takeaways**

- **Production = Workspace service account + domain-wide delegation.** It reads every user's Drive and can check access *as* a user. Personal OAuth is for development only.
- **Always send a `fields` mask** (including `nextPageToken`), or responses look empty.
- **Docs/Sheets → export** (4.3). **PDFs → download** (4.4) and extract the text.
- **The change feed covers content, sharing and lost access**, so one cursor handles all three.
- Inherited folder and shared-drive access is already on each file's list.
- `anyone` = `public` + **overshared** flag. That's our oversharing signal.

**How this connector implements the contract** ([architecture](../architecture/CONNECTORS_ARCHITECTURE.md))

| Method | Calls | Runs |
|---|---|---|
| `sync(cursor)` | 4.2 from the cursor → 4.3 / 4.4 for changed files → ACL from embedded `permissions` (4.5 if missing, 4.7 for groups). First run: 4.1, then save 4.2's start token | every 5 min (content and sharing) |
| `sweep()` | 4.1 with `permissions` → every file ID + ACL (group members cached per run). Safety net only: 4.2 already reports sharing changes and deletions | daily |
| `can_read(credentials, ids)` | 4.6 as that user, batched | each question, final context only |

In Workspace mode, run 4.2 per user (impersonated) or per shared drive
(`driveId=`), each with its own cursor in `sync_state`. One module:
`backend/app/connectors/drive.py`.

**Day-1 checks**

1. Unsharing a file shows up in 4.2 as a change (or `removed: true`).
2. 4.6 as a user without access returns `404`.
3. 4.7 returns nested group members with `includeDerivedMembership=true`.

## 7. Sources

- [Drive API v3 reference (files)](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)
- [Drive API v3 reference (permissions)](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions)
- [Drive API v3 reference (changes.list)](https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/list)
- [Retrieve changes](https://developers.google.com/workspace/drive/api/guides/manage-changes)
- [Share files, folders and drives](https://developers.google.com/workspace/drive/api/guides/manage-sharing)
- [Return specific fields (`fields` mask)](https://developers.google.com/workspace/drive/api/guides/fields-parameter)
- [Domain-wide delegation](https://developers.google.com/workspace/guides/create-credentials#optional_set_up_domain-wide_delegation_for_a_service_account)
- [Directory API: group members](https://developers.google.com/workspace/admin/directory/reference/rest/v1/members/list)
- [Configure the Drive MCP server](https://developers.google.com/workspace/drive/api/guides/configure-mcp-server)
- [Google OAuth Testing mode: 7-day token expiry](https://support.google.com/cloud/answer/15549945?hl=en)

# Slack Connector

## 1. Introduction

Slack holds team chat: messages and threads inside public channels, private
channels and DMs. Our connector uses a **bot** installed in our own workspace
to read every thread's **text** and every channel's **members**, because in
Slack channel membership is the only permission. Removing someone from a
channel is the clearest live-revocation case (challenge scenario 4), and the
live check enforces it on the very next question.

## 2. Glossary

| Term | Meaning |
|---|---|
| Workspace | One Slack organisation, e.g. `ourteam.slack.com`. |
| Full member | A regular workspace user who can see every public channel. |
| Guest | A restricted user (paid plans) who sees **only** the channels they're invited to, including public ones. |
| Public channel | A channel every full member can read, e.g. `#eng`. |
| Private channel | A channel only its members can read, e.g. `#payments-oncall`. |
| DM | A direct conversation between specific people, which a bot can't read unless it's in it, so it's not indexed. |
| Channel ID | The permanent ID of a channel (e.g. `C123`), which never changes even when the name does. |
| User ID | The permanent ID of a person in the workspace, e.g. `U024`. |
| ts | A message's timestamp string (e.g. `1727741000.000100`), which is also its unique ID within the channel. |
| Thread | A parent message plus its replies, linked by the parent's `ts` (`thread_ts`). |
| Bot token | The `xoxb-...` secret our app uses for every call. |
| Scope | One permission the bot is granted, e.g. `groups:history` to read private channels. |
| Internal app | An app installed only in the workspace that built it, which keeps normal rate limits and is allowed to store message data. |
| Mention | How Slack encodes people and channels in text: `<@U024>` and `<#C456\|eng>`. |
| Cursor | `response_metadata.next_cursor`: send it back as `cursor` until it's empty. |
| Principal | A namespaced ID stored in ACLs, e.g. `slack:user:U024` or `slack:members` (every full member). |

## 3. Identity Access Management and Permissions

```
Workspace (ourteam.slack.com)
├── #eng               public  → every full member (not guests)
├── #payments-oncall   private → alice, sara (+ our bot)
└── DM alice ↔ ben             → alice, ben         (not indexed)
```

- There are **no per-message permissions**. Access = channel membership.
- Guests see only channels they were invited to, even public ones.
- The **bot only reads channels it was invited to**. Workspace admins can't read private channels they aren't in either.

**Rule:** you can read a message if you are a member of its channel, or the
channel is public and you are a full member.

## 4. APIs available

| API / tool | What it gives | Use? |
|---|---|---|
| **Web API** (`https://slack.com/api/...`) | Channels, messages, members, users | **Yes** |
| **`slack_sdk`** (official Python SDK) | Typed calls, raises on errors | **Yes** |
| Events API / Socket Mode | Instant message and membership events | Not now: the 30-min sweep meets the ≤ 1 h freshness target. Add it if replies must appear faster |
| Real-Time Search API | Search Slack as one user | No: no membership lists |
| Official Slack MCP server `mcp.slack.com` | Lets an AI agent use Slack **as one signed-in user** | No: can't tell us what *other* users can see |

### Auth / setup

```
1. api.slack.com/apps → Create New App → From scratch → our workspace (keep it internal: never distribute)
2. OAuth & Permissions → Bot scopes:
   channels:read channels:history groups:read groups:history users:read users:read.email
3. Install to Workspace → Bot token (xoxb-) → SLACK_BOT_TOKEN
4. /invite @ourbot in every private channel to be indexed
```

```python
from slack_sdk import WebClient
slack = WebClient(token=SLACK_BOT_TOKEN)
slack.conversations_list(types="public_channel,private_channel")
```

The SDK raises `SlackApiError` when `"ok": false` (raw HTTP returns 200 even on errors).

### 4.1 `conversations.list`: channels the bot can see

| | |
|---|---|
| Request | `GET /conversations.list?types=public_channel,private_channel&limit=200` |

```json
{ "ok": true, "channels": [
  { "id": "C111", "name": "eng", "is_private": false, "is_member": true },
  { "id": "C123", "name": "payments-oncall", "is_private": true, "is_member": true }
], "response_metadata": { "next_cursor": "" } }
```
Notes: index only channels with `is_member: true`.

### 4.2 `conversations.history`: top-level messages in a channel

| | |
|---|---|
| Request | `GET /conversations.history?channel=C123&oldest=<ts>&limit=200` |

```json
{ "ok": true, "messages": [
  { "user": "U024", "text": "Migration blocked by <@U099>", "ts": "1727741000.000100", "reply_count": 2, "latest_reply": "1727741300.000200" }
], "has_more": false, "response_metadata": { "next_cursor": "" } }
```
Notes: replies are **not** included. Use 4.3 when `reply_count > 0`. A new
reply to an old thread changes only that thread's `latest_reply`, and `sweep`
uses that to re-fetch it.

### 4.3 `conversations.replies`: a whole thread

| | |
|---|---|
| Request | `GET /conversations.replies?channel=C123&ts=1727741000.000100` |

Response: same shape as 4.2. The first message is the parent, the rest are replies.

### 4.4 `conversations.members`: who can read a private channel

| | |
|---|---|
| Request | `GET /conversations.members?channel=C123&limit=200` |

```json
{ "ok": true, "members": ["U024", "U077", "UBOT1"], "response_metadata": { "next_cursor": "" } }
```
Notes: includes our bot, so skip bot IDs.

### 4.5 `users.list`: everyone in the workspace

| | |
|---|---|
| Request | `GET /users.list?limit=200` |

```json
{ "ok": true, "members": [
  { "id": "U024", "deleted": false, "is_bot": false, "is_restricted": false, "is_ultra_restricted": false,
    "profile": { "email": "alice@company.com" } }
], "response_metadata": { "next_cursor": "" } }
```
Notes: links identities by email. A full member (not `deleted`, `is_bot`,
`is_restricted` or `is_ultra_restricted`) also gets the `slack:members`
principal on their identity.

## 5. Output Schema Contract

One document per thread (a message with no replies is a thread of one):

```jsonc
{
  "source": "slack",
  "source_id": "C123:1727741000.000100",                    // channel id + ":" + parent ts
  "title": "#payments-oncall",                              // channel name
  "text": "Alice: Migration blocked by Ben\nBen: Fixed, retrying",  // parent + replies, mentions → names
  "url": "https://ourteam.slack.com/archives/C123/p1727741000000100", // workspace + /archives/<channel>/p<ts without dot>
  "updated_at": "2026-09-30T22:05:00Z",                     // latest reply ts, as UTC
  "acl": ["slack:user:U024", "slack:user:U077"]             // public channel: ["slack:members"]
}
```

`acl` = the channel's members from 4.4 (bots removed) for a private channel,
or `["slack:members"]` for a public one.

## 6. Summary

**Takeaways**

- **Access = channel membership.** Public channels go to full members only, not guests.
- **Invite the bot to every private channel to be indexed**, or it's silently skipped.
- **Keep the app internal.** That keeps normal rate limits, and it's the case Slack's API terms allow to store and index messages.
- History has **no replies**. Index whole threads via 4.3, and catch new replies to old threads through `latest_reply`.
- Replace `<@U024>` / `<#C456|eng>` with names before storing text.
- Free plan keeps only **90 days** of messages.

**How this connector implements the contract** ([architecture](../architecture/CONNECTORS_ARCHITECTURE.md))

| Method | Calls | Runs |
|---|---|---|
| `sync(cursor)` | 4.1 → 4.2 `oldest = cursor` per channel → 4.3 for threads → ACL (4.4 cached per channel). New cursor = newest `ts` seen | every 5 min |
| `sweep()` | 4.1 → 4.2 over the retention window: every thread ID + ACL (4.4). Re-fetch (4.3) threads whose `latest_reply` is newer than the stored `updated_at`. 4.5 refreshes `slack:members` identities | every 30 min |
| `can_read(principal, ids)` | 4.4 for each private channel in the final context. Public channel: the user must hold `slack:members` | each question, final context only |

One module: `backend/app/connectors/slack.py`.

**Day-1 checks**

1. After removing a user from a private channel, 4.4 no longer lists them (live check denies).
2. A reply to an old thread raises its parent's `latest_reply` in 4.2.
3. Time 5 calls to 4.2. Expect about 50/min for an internal app (see [TABLE.md](TABLE.md)).

## 7. Sources

- [Slack rate limits for non-Marketplace apps](https://api.slack.com/changelog/2025-05-terms-rate-limit-update-and-faq)
- [Slack API terms on data use (May 2025)](https://www.computerworld.com/article/4005509/salesforce-changes-slack-api-terms-to-block-bulk-data-access-for-llms.html)
- [Slack plans and features (90-day history)](https://slack.com/help/articles/115003205446-Slack-plans-and-features)
- [Slack Web API rate limits](https://docs.slack.dev/apis/web-api/rate-limits/)
- [Slack MCP server and Real-Time Search API](https://slack.com/blog/news/mcp-real-time-search-api-now-available)

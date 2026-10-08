"""Slack connector. API details: docs/connectors/reference/SLACK.md.

Every call uses one person's own user token (store.client): the company admin's for sync and the
scope list, the asking user's for the live check.
"""

import logging
import re
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

log = logging.getLogger(__name__)

MENTION = re.compile(r"<@(U[A-Z0-9]+)>")


def client(token: str) -> WebClient:
    # Default handlers already retry connection errors; add 429 (honours Retry-After).
    c = WebClient(token=token, timeout=30)
    c.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=3))
    return c


def scopes(c: WebClient) -> list[dict]:
    """Channels this person can see, for the admin to choose the boundary from."""
    return [{"id": ch["id"], "title": f"#{ch['name']}"}
            for page in c.conversations_list(types="public_channel,private_channel", exclude_archived=True, limit=200)
            for ch in page["channels"]]


def fetch(c: WebClient, channel: str, changed: Callable[[str, str], bool] = lambda *_: True) -> Iterator[dict]:
    """One document per thread (docs/connectors/reference/SLACK.md section 5). Replies are downloaded only for
    threads that `changed(source_id, updated_at)`; the others get `text` None."""
    info = c.conversations_info(channel=channel)["channel"]
    members = [f"slack:user:{m}" for page in c.conversations_members(channel=channel, limit=1000)
               for m in page["members"]]
    # Public: every full member, plus guests who joined (they are in the member list).
    acl = members if info["is_private"] else ["slack:members", *members]
    workspace = c.auth_test()["url"]  # https://<team>.slack.com/
    names: dict[str, str] = {}

    def name(user: str) -> str:
        if user not in names:
            try:
                u = c.users_info(user=user)["user"]
                names[user] = u.get("real_name") or u["name"]
            except SlackApiError:
                names[user] = user
        return names[user]

    def line(m: dict) -> str:
        return f"{name(m.get('user', '?'))}: {MENTION.sub(lambda x: '@' + name(x[1]), m.get('text', ''))}"

    for page in c.conversations_history(channel=channel, limit=200):
        for m in page["messages"]:
            if m.get("subtype"):  # joins, bot posts, ...
                continue
            source_id = f"{channel}:{m['ts']}"
            # Newest of: posted, last reply, first message edited. An edited reply keeps its old
            # text until the thread gets a new reply.
            last = max(m["ts"], m.get("latest_reply", "0"), m.get("edited", {}).get("ts", "0"), key=float)
            updated_at = datetime.fromtimestamp(float(last), UTC).isoformat()
            body = None
            if changed(source_id, updated_at):
                thread = [m]
                if m.get("reply_count"):
                    thread = [r for p in c.conversations_replies(channel=channel, ts=m["ts"], limit=200)
                              for r in p["messages"]]
                body = "\n".join(line(r) for r in thread if not r.get("subtype"))
            yield {
                "source": "slack",
                "source_id": source_id,
                "scope_id": channel,
                "title": f"#{info['name']}",
                "url": f"{workspace}archives/{channel}/p{m['ts'].replace('.', '')}",
                "updated_at": updated_at,
                "acl": acl,
                "text": body,
            }


def can_read(c: WebClient, ids: Iterable[str]) -> set[str]:
    """Live check (ADR-003): which of these threads (`<channel>:<ts>`) the token's owner can read now.

    Slack answers "channel_not_found" for a private channel they are not in, and for a public one when
    they are a guest who has not joined it. Deny by default: any error leaves the channel out.
    """
    ids = list(ids)

    def readable(channel: str) -> bool:
        try:
            c.conversations_info(channel=channel)
            return True
        except SlackApiError as e:
            log.info("Slack check for %s: %s", channel, e.response.get("error"))
            return False

    channels = list({i.split(":", 1)[0] for i in ids})
    # In parallel: the live check has about 2 seconds for every source together.
    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = {ch for ch, ok in zip(channels, pool.map(readable, channels), strict=True) if ok}
    return {i for i in ids if i.split(":", 1)[0] in allowed}

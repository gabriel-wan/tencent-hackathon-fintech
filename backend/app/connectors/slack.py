"""Slack connector. API details: docs/connectors/SLACK.md."""

import logging
import os
from collections.abc import Iterable
from functools import lru_cache

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

log = logging.getLogger(__name__)

SCOPES = {"channels:read", "channels:history", "groups:read", "groups:history", "users:read", "users:read.email"}


def client(token: str) -> WebClient:
    """Client for any Slack token (the workspace bot, or later a user's sign-in token)."""
    # Default handlers already retry connection errors; add 429 (honours Retry-After).
    c = WebClient(token=token, timeout=30)
    c.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=3))
    return c


@lru_cache
def bot() -> WebClient:
    """The workspace bot the admin installed (ADR-002): reads channels inside the boundary."""
    return client(os.environ["SLACK_BOT_TOKEN"])


def ping() -> str:
    resp = bot().auth_test()
    headers = {k.lower(): v for k, v in resp.headers.items()}
    granted = {s.strip() for s in headers.get("x-oauth-scopes", "").split(",")}
    if missing := SCOPES - granted:
        raise PermissionError(f"bot lacks scopes {', '.join(sorted(missing))}: add them and reinstall the app")
    return f"as {resp['user']} in {resp['team']}"


def can_read(user_id: str, channel_ids: Iterable[str]) -> set[str]:
    """Live check (ADR-003): which of these channels Slack user `user_id` can read right now.

    Public channel: any full member, or a guest who joined it. Private channel: members only.
    Uses the bot, so only the user's Slack ID (from their Slack sign-in) is needed.
    Deny by default: any error for a channel leaves it out.
    """
    c = bot()
    try:
        user = c.users_info(user=user_id)["user"]
    except SlackApiError as e:
        log.warning("Slack users.info failed, denying all: %s", e.response.get("error"))
        return set()
    full_member = not any(user.get(k) for k in ("deleted", "is_bot", "is_restricted", "is_ultra_restricted"))

    allowed = set()
    for channel in set(channel_ids):
        try:
            if full_member and not c.conversations_info(channel=channel)["channel"]["is_private"]:
                allowed.add(channel)
            elif any(user_id in page["members"] for page in c.conversations_members(channel=channel, limit=1000)):
                allowed.add(channel)
        except SlackApiError as e:
            log.warning("Slack check for %s failed, denying: %s", channel, e.response.get("error"))
    return allowed

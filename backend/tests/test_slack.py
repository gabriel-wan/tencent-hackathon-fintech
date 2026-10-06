"""Slack connector: fetch (threads and ACL) and the live check, against a fake workspace. No real API calls."""

import pytest
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_handlers import (
    ConnectionErrorRetryHandler,
    RateLimitErrorRetryHandler,
)

from app.connectors import slack


def test_client_retries_rate_limits_and_connection_errors():
    handlers = {type(h) for h in slack.client("xoxp-user-token").retry_handlers}
    assert {RateLimitErrorRetryHandler, ConnectionErrorRetryHandler} <= handlers


def slack_error(error):
    return SlackApiError(error, {"ok": False, "error": error})


class FakeSlack:
    """One person's view of the workspace. C-PUB public, C-PRIV private; `visible` = channels they can open."""

    def __init__(self, visible=("C-PUB", "C-PRIV")):
        self.visible = set(visible)

    def conversations_info(self, channel):
        if channel not in self.visible:
            raise slack_error("channel_not_found")
        return {"channel": {"name": channel.lower(), "is_private": channel == "C-PRIV"}}

    def conversations_members(self, channel, limit):
        return iter([{"members": ["U1"]}, {"members": ["U2"]}])  # SlackResponse pages iterate like this

    def auth_test(self):
        return {"url": "https://corp.slack.com/"}

    def users_info(self, user):
        return {"user": {"name": user.lower(), "real_name": {"U1": "Alice", "U2": "Ben"}[user]}}

    def conversations_history(self, channel, limit):
        return iter([{"messages": [
            {"user": "U1", "text": "Migration blocked by <@U2>", "ts": "1727741000.000100", "reply_count": 1,
             "latest_reply": "1727741300.000200"},
            {"subtype": "channel_join", "user": "U2", "text": "joined", "ts": "1727740000.000100"},
        ]}])

    def conversations_replies(self, channel, ts, limit):
        return iter([{"messages": [{"user": "U1", "text": "Migration blocked by <@U2>", "ts": ts},
                                   {"user": "U2", "text": "Fixed, retrying", "ts": "1727741300.000200"}]}])


def test_fetch_one_document_per_thread():
    [doc] = slack.fetch(FakeSlack(), "C-PRIV")  # the join message is not a thread
    assert doc["updated_at"].startswith("2024-10-01T00:08:20")  # the latest reply, in UTC
    assert {k: v for k, v in doc.items() if k != "updated_at"} == {
        "source": "slack", "source_id": "C-PRIV:1727741000.000100", "scope_id": "C-PRIV", "title": "#c-priv",
        "url": "https://corp.slack.com/archives/C-PRIV/p1727741000000100",
        "acl": ["slack:user:U1", "slack:user:U2"],  # private: members only
        "text": "Alice: Migration blocked by @Ben\nBen: Fixed, retrying",
    }


def test_unchanged_thread_is_not_downloaded_again():
    fake = FakeSlack()
    fake.conversations_replies = lambda **_: pytest.fail("replies of an unchanged thread were downloaded")
    [doc] = slack.fetch(fake, "C-PRIV", lambda *_: False)
    assert doc["text"] is None and doc["acl"] == ["slack:user:U1", "slack:user:U2"]  # permissions still refreshed


def test_public_channel_is_open_to_every_full_member_and_joined_guests():
    [doc] = slack.fetch(FakeSlack(), "C-PUB")
    assert doc["acl"] == ["slack:members", "slack:user:U1", "slack:user:U2"]


@pytest.mark.parametrize(("visible", "expected"), [
    (("C-PUB", "C-PRIV"), {"C-PUB:1", "C-PUB:2", "C-PRIV:1"}),
    (("C-PUB",), {"C-PUB:1", "C-PUB:2"}),  # not in the private channel
    ((), set()),  # e.g. a guest who joined neither
])
def test_can_read_asks_slack_as_the_user(visible, expected):
    assert slack.can_read(FakeSlack(visible), ["C-PUB:1", "C-PUB:2", "C-PRIV:1"]) == expected

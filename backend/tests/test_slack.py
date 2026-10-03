"""Slack client, ping scope check and live access check. No real API calls (bot replaced by a stub)."""

import pytest
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_handlers import ConnectionErrorRetryHandler, RateLimitErrorRetryHandler

from app.connectors import slack


def test_bot_requires_config():
    with pytest.raises(KeyError, match="SLACK_BOT_TOKEN"):
        slack.bot()


def test_client_retries_rate_limits_and_connection_errors():
    handlers = {type(h) for h in slack.client("xoxp-user-token").retry_handlers}
    assert {RateLimitErrorRetryHandler, ConnectionErrorRetryHandler} <= handlers


class FakeResponse(dict):
    def __init__(self, scopes):
        super().__init__(user="brainbot", team="ourteam")
        self.headers = {"X-OAuth-Scopes": scopes}


def use_bot(monkeypatch, bot):
    monkeypatch.setattr(slack, "bot", lambda: bot)


def test_ping_ok_with_all_scopes(monkeypatch):
    scopes = ",".join(sorted(slack.SCOPES)) + ",chat:write"
    use_bot(monkeypatch, type("Bot", (), {"auth_test": lambda self: FakeResponse(scopes)})())
    assert slack.ping() == "as brainbot in ourteam"


def test_ping_fails_when_scope_missing(monkeypatch):
    use_bot(monkeypatch, type("Bot", (), {"auth_test": lambda self: FakeResponse("channels:read, channels:history")})())
    with pytest.raises(PermissionError, match="groups:history"):
        slack.ping()


# Workspace for can_read: C-PUB public, C-PRIV private (alice only), C-GONE deleted channel.
USERS = {
    "U-ALICE": {},  # full member
    "U-GUEST": {"is_restricted": True},  # guest, joined C-PUB only
    "U-EX": {"deleted": True},  # deactivated
}
CHANNELS = {"C-PUB": False, "C-PRIV": True}  # channel -> is_private
MEMBERS = {"C-PUB": [["U-ALICE"], ["U-GUEST"]], "C-PRIV": [["U-BOB"], ["U-ALICE"]]}  # two pages each


def slack_error(error):
    return SlackApiError(error, {"ok": False, "error": error})


class FakeBot:
    def users_info(self, user):
        if user not in USERS:
            raise slack_error("user_not_found")
        return {"user": USERS[user]}

    def conversations_info(self, channel):
        if channel not in CHANNELS:
            raise slack_error("channel_not_found")
        return {"channel": {"is_private": CHANNELS[channel]}}

    def conversations_members(self, channel, limit):
        if channel not in MEMBERS:
            raise slack_error("channel_not_found")
        return ({"members": page} for page in MEMBERS[channel])  # SlackResponse pages iterate like this


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        ("U-ALICE", {"C-PUB", "C-PRIV"}),  # full member: public + her private channel
        ("U-GUEST", {"C-PUB"}),  # guest: only the public channel she joined
        ("U-EX", set()),  # deactivated: nothing
        ("U-NOBODY", set()),  # unknown user: deny all
    ],
)
def test_can_read(monkeypatch, user, expected):
    use_bot(monkeypatch, FakeBot())
    assert slack.can_read(user, ["C-PUB", "C-PRIV", "C-GONE"]) == expected


def test_can_read_guest_not_in_public_channel(monkeypatch):
    use_bot(monkeypatch, FakeBot())
    monkeypatch.setitem(MEMBERS, "C-PUB", [["U-ALICE"]])
    assert slack.can_read("U-GUEST", ["C-PUB"]) == set()


def test_can_read_private_non_member(monkeypatch):
    use_bot(monkeypatch, FakeBot())
    monkeypatch.setitem(USERS, "U-BOB2", {})
    assert slack.can_read("U-BOB2", ["C-PRIV"]) == set()

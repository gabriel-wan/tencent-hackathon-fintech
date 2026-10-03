"""`python -m app.connectors`: failure messages, exit codes, one source never blocking another."""

import httplib2
import httpx
import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from slack_sdk.errors import SlackApiError

from app.connectors import __main__ as cli


def http_error(status):
    request = httpx.Request("GET", "https://example.atlassian.net/rest/api/3/myself")
    return httpx.HTTPStatusError("x", request=request, response=httpx.Response(status, request=request))


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (KeyError("ATLASSIAN_API_TOKEN"), "not configured: set ATLASSIAN_API_TOKEN in backend/.env"),
        (KeyError("GOOGLE_REFRESH_TOKEN"), "or GOOGLE_SERVICE_ACCOUNT_JSON for Workspace mode"),
        (KeyError("displayName"), "KeyError: 'displayName'"),  # bad API response, not missing config
        (http_error(401), "HTTP 401 /rest/api/3/myself (auth failed"),
        (http_error(404), "check ATLASSIAN_BASE_URL"),
        (http_error(500), "HTTP 500 /rest/api/3/myself"),
        (SlackApiError("x", {"ok": False, "error": "invalid_auth"}), "Slack error: invalid_auth"),
        (HttpError(httplib2.Response({"status": 404}), b'{"error": {"message": "File not found"}}'), "HTTP 404"),
        (RefreshError("invalid_grant"), "auth failed: invalid_grant"),
        (PermissionError("not a Jira admin"), "PermissionError: not a Jira admin"),
    ],
)
def test_reason(error, expected):
    assert expected in cli.reason(error)


def test_unknown_connector(capsys):
    assert cli.main(["jira", "teams"]) == 2
    assert "unknown connector(s): teams" in capsys.readouterr().out


def test_one_failure_does_not_stop_others(monkeypatch, capsys):
    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "PINGS", {"a": lambda: "as bot", "b": broken, "c": lambda: "as bot"})
    assert cli.main([]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "OK   a          as bot",
        "FAIL b          RuntimeError: boom",
        "OK   c          as bot",
    ]


def test_all_ok_exits_zero(monkeypatch):
    monkeypatch.setattr(cli, "PINGS", {"a": lambda: "as bot"})
    assert cli.main([]) == 0


def test_unconfigured_sources_fail_without_network(capsys):
    # conftest removed every credential, so each real ping must stop at config, before any request.
    assert cli.main([]) == 1
    out = capsys.readouterr().out
    assert out.count("not configured") == len(cli.PINGS)

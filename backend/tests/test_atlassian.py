"""Shared Atlassian client (retries) plus Jira and Confluence ping. No real API calls."""

import httpx
import pytest

from app.connectors import atlassian, confluence, jira


def replay(*responses):
    """Handler returning the given responses in order."""
    it = iter(responses)
    return lambda request: next(it)


def test_client_requires_config():
    with pytest.raises(KeyError, match="ATLASSIAN_BASE_URL"):
        atlassian.client()


def test_rate_limit_retried_after_retry_after(atlassian_api):
    sent, sleeps = atlassian_api(replay(httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)))
    assert atlassian.request("GET", "/rest/api/3/myself").status_code == 200
    assert len(sent) == 2
    assert sleeps == [7.0]


def test_gives_up_after_max_attempts(atlassian_api):
    sent, sleeps = atlassian_api(replay(*[httpx.Response(503)] * atlassian.MAX_ATTEMPTS))
    with pytest.raises(httpx.HTTPStatusError):
        atlassian.request("GET", "/rest/api/3/myself")
    assert len(sent) == atlassian.MAX_ATTEMPTS
    assert sleeps == [1, 2]  # exponential backoff, none after the last attempt


def test_network_error_retried_then_raised(atlassian_api):
    def down(request):
        raise httpx.ConnectError("down", request=request)

    sent, _ = atlassian_api(down)
    with pytest.raises(httpx.ConnectError):
        atlassian.request("GET", "/rest/api/3/myself")
    assert len(sent) == atlassian.MAX_ATTEMPTS


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_raise_without_retry(atlassian_api, status):
    sent, sleeps = atlassian_api(replay(httpx.Response(status)))
    with pytest.raises(httpx.HTTPStatusError):
        atlassian.request("GET", "/rest/api/3/myself")
    assert len(sent) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("retry_after", "attempt", "expected"),
    [
        ("5", 0, 5),
        ("-3", 0, 0),  # never negative (time.sleep would raise)
        ("999", 0, atlassian.MAX_WAIT_S),  # capped
        ("Wed, 21 Oct 2026 07:28:00 GMT", 0, 1),  # HTTP-date form falls back to backoff
        (None, 1, 2),
        (None, 10, atlassian.MAX_WAIT_S),
    ],
)
def test_wait(retry_after, attempt, expected):
    assert atlassian._wait(attempt, retry_after) == expected


def jira_site(admin):
    def handler(request):
        if request.url.path == "/rest/api/3/myself":
            return httpx.Response(200, json={"displayName": "Ben"})
        assert request.url.params["permissions"] == "ADMINISTER"
        return httpx.Response(200, json={"permissions": {"ADMINISTER": {"havePermission": admin}}})

    return handler


def test_jira_ping_admin(atlassian_api):
    atlassian_api(jira_site(admin=True))
    assert jira.ping() == "as Ben (admin)"


def test_jira_ping_rejects_non_admin(atlassian_api):
    atlassian_api(jira_site(admin=False))
    with pytest.raises(PermissionError, match="not a Jira admin"):
        jira.ping()


def test_confluence_ping(atlassian_api):
    atlassian_api(replay(httpx.Response(200, json={"type": "known", "displayName": "Ben"})))
    assert confluence.ping() == "as Ben"


def test_confluence_ping_rejects_anonymous(atlassian_api):
    atlassian_api(replay(httpx.Response(200, json={"type": "anonymous", "displayName": "Anonymous"})))
    with pytest.raises(PermissionError, match="anonymous"):
        confluence.ping()

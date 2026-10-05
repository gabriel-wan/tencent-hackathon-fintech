"""Shared Atlassian client (retries), and the Jira and Confluence connectors. No real API calls."""

import json

import httpx
import pytest

from app.connectors import atlassian, confluence, jira


def replay(*responses):
    """Handler returning the given responses in order."""
    it = iter(responses)
    return lambda request: next(it)


def test_rate_limit_retried_after_retry_after(atlassian_api):
    http, sent, sleeps = atlassian_api(replay(httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)))
    assert atlassian.request("GET", "/rest/api/3/myself", http=http).status_code == 200
    assert len(sent) == 2
    assert sleeps == [7.0]


def test_gives_up_after_max_attempts(atlassian_api):
    http, sent, sleeps = atlassian_api(replay(*[httpx.Response(503)] * atlassian.MAX_ATTEMPTS))
    with pytest.raises(httpx.HTTPStatusError):
        atlassian.request("GET", "/rest/api/3/myself", http=http)
    assert len(sent) == atlassian.MAX_ATTEMPTS
    assert sleeps == [1, 2]  # exponential backoff, none after the last attempt


def test_network_error_retried_then_raised(atlassian_api):
    def down(request):
        raise httpx.ConnectError("down", request=request)

    http, sent, _ = atlassian_api(down)
    with pytest.raises(httpx.ConnectError):
        atlassian.request("GET", "/rest/api/3/myself", http=http)
    assert len(sent) == atlassian.MAX_ATTEMPTS


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_raise_without_retry(atlassian_api, status):
    http, sent, sleeps = atlassian_api(replay(httpx.Response(status)))
    with pytest.raises(httpx.HTTPStatusError):
        atlassian.request("GET", "/rest/api/3/myself", http=http)
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


def site(routes):
    """A fake site: routes maps "METHOD path" to a JSON body, or to a function(request) -> body."""
    def handler(request):
        route = routes[f"{request.method} {request.url.path}"]
        return httpx.Response(200, json=route(request) if callable(route) else route)

    return handler


# ---- Jira ----

def doc(*paragraphs):
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": p}]}
                                       for p in paragraphs]}


def test_adf_text_one_line_per_block():
    assert jira.adf_text(doc("Card charged twice.", "Refund issued.")) == "Card charged twice.\nRefund issued.\n"
    assert jira.adf_text(None) == ""


def test_jira_fetch_one_document_per_ticket(atlassian_api):
    def search(request):
        body = json.loads(request.content)
        assert body["jql"] == 'project = "PAY"'
        if "nextPageToken" not in body:  # two pages
            return {"issues": [], "nextPageToken": "p2"}
        return {"issues": [{"id": "10013", "key": "PAY-13", "fields": {
            "summary": "Double charge", "description": doc("Card charged twice."), "updated": "2026-10-01T09:00:00.000+0800",
            "comment": {"comments": [{"body": doc("Refund issued.")}]}}}]}

    http, _, _ = atlassian_api(site({
        "GET /rest/api/3/serverInfo": {"baseUrl": "https://corp.atlassian.net"},
        "GET /rest/api/3/user/permission/search": [{"accountId": "A1"}, {"accountId": "A2"}],
        "POST /rest/api/3/search/jql": search,
    }))
    assert list(jira.fetch(http, "PAY")) == [{
        "source": "jira", "source_id": "10013", "scope_id": "PAY", "title": "PAY-13: Double charge",
        "url": "https://corp.atlassian.net/browse/PAY-13", "updated_at": "2026-10-01T09:00:00.000+0800",
        "acl": ["atlassian:user:A1", "atlassian:user:A2"],
        "text": "Double charge\nCard charged twice.\n\nRefund issued.",
    }]


def test_jira_can_read_asks_for_the_users_permissions_in_one_call(atlassian_api):
    def check(request):
        assert json.loads(request.content)["projectPermissions"][0]["issues"] == [10013, 10014]
        return {"projectPermissions": [{"permission": "BROWSE_PROJECTS", "issues": [10013]}]}

    http, sent, _ = atlassian_api(site({"POST /rest/api/3/permissions/check": check}))
    assert jira.can_read(http, ["10013", "10014", "not-an-id"]) == {"10013"}
    assert len(sent) == 1


# ---- Confluence ----

def test_storage_text():
    assert confluence.storage_text("<p>Step 1: <strong>fail over</strong> &amp; check</p><p>Done</p>") == \
        "Step 1: fail over & check\nDone"


def restricted(users=(), groups=()):
    return {"restrictions": {"user": {"results": [{"accountId": u} for u in users]},
                             "group": {"results": [{"id": g} for g in groups]}}}


def confluence_site(restrictions):
    """Space S1: page 1 (Runbook) and its child page 2, under a folder F that is not a page."""
    pages = [{"id": "1", "parentId": "F", "title": "Runbook", "version": {"createdAt": "2026-10-01T13:05:00Z"},
              "body": {"storage": {"value": "<p>Fail over</p>"}}, "_links": {"webui": "/pages/1"}},
             {"id": "2", "parentId": "1", "title": "Child", "version": {"createdAt": "2026-10-01T13:05:00Z"},
              "body": {"storage": {"value": "<p>Secret</p>"}}, "_links": {"webui": "/pages/2"}}]
    routes = {
        "GET /wiki/api/v2/spaces/S1/pages": {"results": pages, "_links": {"base": "https://corp.atlassian.net/wiki"}},
        "GET /wiki/rest/api/group/G1/membersByGroupId": {"results": [{"accountId": "A3"}]},
    }
    for page in ("1", "2"):
        routes[f"GET /wiki/rest/api/content/{page}/restriction/byOperation/read"] = restrictions.get(page, restricted())
    return site(routes)


def acls(http):
    return {d["source_id"]: d["acl"] for d in confluence.fetch(http, "S1")}


def test_confluence_fetch_downloads_text_only_for_changed_pages(atlassian_api):
    http, sent, _ = atlassian_api(confluence_site({}))
    docs = {d["source_id"]: d for d in confluence.fetch(http, "S1", lambda source_id, _updated: source_id == "2")}
    assert docs["1"]["text"] is None and docs["2"]["text"] == "Secret"
    assert docs["2"]["url"] == "https://corp.atlassian.net/wiki/pages/2"
    assert len(sent) == 3  # the listing, then one restriction check per page: nothing else per page


def test_confluence_unrestricted_pages_are_for_the_whole_company(atlassian_api):
    http, _, _ = atlassian_api(confluence_site({}))
    assert acls(http) == {"1": ["public"], "2": ["public"]}


def test_confluence_restriction_is_inherited_and_groups_expanded(atlassian_api):
    http, _, _ = atlassian_api(confluence_site({"1": restricted(users=["A1"], groups=["G1"])}))
    assert acls(http) == {"1": ["atlassian:user:A1", "atlassian:user:A3"],
                          "2": ["atlassian:user:A1", "atlassian:user:A3"]}  # the parent's restriction applies


def test_confluence_deepest_restriction_wins(atlassian_api):
    http, _, _ = atlassian_api(confluence_site({"1": restricted(users=["A1", "A2"]), "2": restricted(users=["A2"])}))
    assert acls(http)["2"] == ["atlassian:user:A2"]


def test_links_pages_follows_the_next_cursor(atlassian_api):
    # Regression (real run): the cursor in `_links.next` was dropped, so page 1 came back forever.
    def spaces(request):
        if request.url.params.get("cursor") == "B":
            return {"results": [{"id": "2"}], "_links": {"base": "https://corp.atlassian.net/wiki"}}
        return {"results": [{"id": "1"}], "_links": {"next": "/wiki/api/v2/spaces?cursor=B&limit=1"}}

    http, _, _ = atlassian_api(site({"GET /wiki/api/v2/spaces": spaces}))
    assert [s["id"] for s in atlassian.links_pages(http, "/wiki/api/v2/spaces", limit=1)] == ["1", "2"]


def test_confluence_can_read_is_one_search_as_the_user(atlassian_api):
    def search(request):
        assert request.url.params["cql"] == "id in (1,2)"
        return {"results": [{"content": {"id": "1"}}]}

    http, sent, _ = atlassian_api(site({"GET /wiki/rest/api/search": search}))
    assert confluence.can_read(http, ["1", "2", "x); delete"]) == {"1"}  # non-numeric IDs never reach CQL
    assert len(sent) == 1

"""Shared HTTP client for Jira and Confluence: one person's OAuth sign-in (ADR-002), which reaches a
site through api.atlassian.com/ex/<product>/<cloud id>. Built by store.client().
"""

import logging
import time
from collections.abc import Iterator

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 502, 503, 504}
MAX_ATTEMPTS = 3
MAX_WAIT_S = 30


def user_client(access_token: str, product: str, cloud_id: str) -> httpx.Client:
    """`product` is "jira" or "confluence"; paths are the site's REST paths."""
    return httpx.Client(
        base_url=f"https://api.atlassian.com/ex/{product}/{cloud_id}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=30,
    )


def _wait(attempt: int, retry_after: str | None) -> float:
    try:
        return min(max(float(retry_after), 0), MAX_WAIT_S)
    except (TypeError, ValueError):
        return min(2**attempt, MAX_WAIT_S)


def request(method: str, path: str, *, http: httpx.Client, **kwargs) -> httpx.Response:
    """Send a request, retrying rate limits and transient failures; raise on any other error."""
    for attempt in range(MAX_ATTEMPTS):
        last = attempt == MAX_ATTEMPTS - 1
        try:
            resp = http.request(method, path, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as e:  # transient only; bad URL etc. raise at once
            if last:
                raise
            cause, wait = type(e).__name__, _wait(attempt, None)
        else:
            if resp.status_code not in RETRY_STATUSES or last:
                return resp.raise_for_status()
            cause, wait = f"HTTP {resp.status_code}", _wait(attempt, resp.headers.get("Retry-After"))
        # Path only: query params and bodies may hold user data.
        log.warning("Atlassian %s %s: %s, retry %d/%d in %.1fs",
                    method, path, cause, attempt + 1, MAX_ATTEMPTS - 1, wait)
        time.sleep(wait)


def get(http: httpx.Client, path: str, **params):
    # None, not {}: httpx replaces the path's own query string (e.g. a `_links.next` cursor) with any params dict.
    return request("GET", path, http=http, params=params or None).json()


def pages(http: httpx.Client, path: str, key: str | None, start: str = "startAt", size: str = "maxResults",
          page: int = 100, **params) -> Iterator[dict]:
    """Items of an offset-paged list. `key` names the list in the response (None: the response is the list)."""
    offset = 0
    while True:
        resp = get(http, path, **params, **{start: offset, size: page})
        items = resp[key] if key else resp
        yield from items
        if len(items) < page:
            return
        offset += page


def links_pages(http: httpx.Client, path: str | None, **params) -> Iterator[dict]:
    """Items of a Confluence v2 list, following `_links.next`. Each item's `_links.base` is set to the
    site's URL (given once per response), so `base + webui` is its link."""
    while path:
        resp = get(http, path, **params)
        links = resp.get("_links", {})
        for item in resp["results"]:
            item.setdefault("_links", {})["base"] = links.get("base", "")
            yield item
        path, params = links.get("next"), {}

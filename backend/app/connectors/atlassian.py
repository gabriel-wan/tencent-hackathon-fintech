"""Shared HTTP clients for Jira and Confluence.

client(): the admin's API token for one site (env). user_client(): a user's OAuth sign-in
(ADR-002), which reaches a site through api.atlassian.com/ex/<product>/<cloud id>.
"""

import logging
import os
import time
from functools import lru_cache

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 502, 503, 504}
MAX_ATTEMPTS = 3
MAX_WAIT_S = 30


@lru_cache
def client() -> httpx.Client:
    return httpx.Client(
        base_url=os.environ["ATLASSIAN_BASE_URL"],
        auth=(os.environ["ATLASSIAN_EMAIL"], os.environ["ATLASSIAN_API_TOKEN"]),
        headers={"Accept": "application/json"},
        timeout=30,
    )


def user_client(access_token: str, product: str, cloud_id: str) -> httpx.Client:
    """`product` is "jira" or "confluence"; paths are then the same as with client()."""
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


def request(method: str, path: str, *, http: httpx.Client | None = None, **kwargs) -> httpx.Response:
    """Send a request (admin client unless `http` is given), retrying rate limits and transient
    failures; raise on any other error."""
    http = http or client()
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

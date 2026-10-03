"""Ping connectors: python -m app.connectors [jira confluence drive slack]"""

import logging
import os
import sys

import httpx
from google.auth.exceptions import GoogleAuthError
from googleapiclient.errors import HttpError
from slack_sdk.errors import SlackApiError

from app.connectors import confluence, drive, jira, slack

PINGS = {"jira": jira.ping, "confluence": confluence.ping, "drive": drive.ping, "slack": slack.ping}
AUTH_HINT = " (auth failed: check ATLASSIAN_EMAIL/ATLASSIAN_API_TOKEN)"
HINTS = {401: AUTH_HINT, 403: AUTH_HINT, 404: " (check ATLASSIAN_BASE_URL and that the product is on this site)"}


def reason(e: Exception) -> str:
    if isinstance(e, KeyError) and str(e.args[0]).startswith(("ATLASSIAN_", "GOOGLE_", "SLACK_")):
        alt = " (or GOOGLE_SERVICE_ACCOUNT_JSON for Workspace mode)" if e.args[0] == "GOOGLE_REFRESH_TOKEN" else ""
        return f"not configured: set {e.args[0]} in backend/.env{alt}"
    if isinstance(e, SlackApiError):
        return f"Slack error: {e.response.get('error')}"  # e.g. invalid_auth, not_authed
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        hint = HINTS.get(code, "")
        return f"HTTP {code} {e.request.url.path}{hint}"
    if isinstance(e, HttpError):
        return f"HTTP {e.status_code}: {e.reason}"
    if isinstance(e, GoogleAuthError):
        return f"auth failed: {e}"
    return f"{type(e).__name__}: {e}"


def main(names: list[str]) -> int:
    unknown = set(names) - PINGS.keys()
    if unknown:
        print(f"unknown connector(s): {', '.join(sorted(unknown))}; choose from {', '.join(PINGS)}")
        return 2
    failed = False
    for name in names or PINGS:
        try:
            print(f"OK   {name:<10} {PINGS[name]()}")
        except Exception as e:  # report every source, never crash on one
            failed = True
            print(f"FAIL {name:<10} {reason(e)}")
    return int(failed)


def setup_logging() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "info").upper(), format="%(levelname)s %(name)s: %(message)s")
    # Library debug logs include full response bodies (messages, file text): never let them through.
    for lib in ("httpx", "httpcore", "googleapiclient", "google", "slack_sdk", "urllib3"):
        logging.getLogger(lib).setLevel(logging.WARNING)


if __name__ == "__main__":
    setup_logging()
    sys.exit(main(sys.argv[1:]))

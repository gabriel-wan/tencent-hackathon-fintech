"""Confluence connector. API details: docs/connectors/CONFLUENCE.md."""

from app.connectors.atlassian import request


def ping() -> str:
    me = request("GET", "/wiki/rest/api/user/current").json()
    if me.get("type") == "anonymous":  # sites with anonymous access answer 200 instead of 401
        raise PermissionError("token not accepted: request ran as anonymous")
    return f"as {me['displayName']}"

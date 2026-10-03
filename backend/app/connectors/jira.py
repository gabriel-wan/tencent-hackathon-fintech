"""Jira connector. API details: docs/connectors/JIRA.md."""

from app.connectors.atlassian import request


def ping() -> str:
    me = request("GET", "/rest/api/3/myself").json()
    perms = request("GET", "/rest/api/3/mypermissions", params={"permissions": "ADMINISTER"}).json()
    if not perms["permissions"]["ADMINISTER"]["havePermission"]:
        raise PermissionError(f"{me['displayName']} is not a Jira admin; permission sync needs an admin token")
    return f"as {me['displayName']} (admin)"

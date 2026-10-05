"""Jira connector. API details: docs/connectors/JIRA.md.

Every call uses one person's own Atlassian sign-in (store.client): the company admin's for sync and
the scope list, the asking user's for the live check.
"""

from collections.abc import Callable, Iterable, Iterator

import httpx

from app.connectors.atlassian import get, pages, request

BLOCKS = {"paragraph", "heading", "codeBlock", "listItem", "blockquote", "tableRow"}


def adf_text(node: dict | None) -> str:
    """Atlassian Document Format -> plain text, one line per block."""
    if not node:
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    inner = "".join(adf_text(c) for c in node.get("content") or [])
    return inner + "\n" if node.get("type") in BLOCKS else inner


def scopes(http: httpx.Client) -> list[dict]:
    """Projects this person can see, for the admin to choose the boundary from."""
    return [{"id": p["key"], "title": p["name"]} for p in pages(http, "/rest/api/3/project/search", "values")]


def fetch(http: httpx.Client, project: str, changed: Callable[[str, str], bool] = lambda *_: True) -> Iterator[dict]:
    """One document per ticket (docs/connectors/JIRA.md section 5); `text` None if not `changed`."""
    site = get(http, "/rest/api/3/serverInfo")["baseUrl"]
    # Jira expands groups and roles itself. ponytail: issue security levels are not applied, so this
    # may be too wide for restricted tickets; the live check trims it.
    acl = [f"atlassian:user:{u['accountId']}" for u in pages(
        http, "/rest/api/3/user/permission/search", None, permissions="BROWSE_PROJECTS", projectKey=project)]
    body = {"jql": f'project = "{project}"', "fields": ["summary", "description", "comment", "updated"],
            "maxResults": 100}
    while True:
        resp = request("POST", "/rest/api/3/search/jql", http=http, json=body).json()
        for issue in resp["issues"]:
            f = issue["fields"]
            body = None
            if changed(issue["id"], f["updated"]):
                comments = [adf_text(c["body"]) for c in (f.get("comment") or {}).get("comments", [])]
                body = "\n".join([f["summary"], adf_text(f.get("description")), *comments]).strip()
            yield {
                "source": "jira",
                "source_id": issue["id"],  # numeric: what the live check (bulk permissions) takes
                "scope_id": project,
                "title": f"{issue['key']}: {f['summary']}",
                "url": f"{site}/browse/{issue['key']}",
                "updated_at": f["updated"],
                "acl": acl,
                "text": body,
            }
        if not (token := resp.get("nextPageToken")):
            return
        body["nextPageToken"] = token


def can_read(http: httpx.Client, ids: Iterable[str]) -> set[str]:
    """Live check (ADR-003): which of these tickets the sign-in's owner can browse right now (one call)."""
    issues = [int(i) for i in ids if i.isdigit()]
    if not issues:
        return set()
    resp = request("POST", "/rest/api/3/permissions/check", http=http, json={
        "projectPermissions": [{"permissions": ["BROWSE_PROJECTS"], "issues": issues}]}).json()
    return {str(i) for p in resp.get("projectPermissions", []) for i in p.get("issues", [])}

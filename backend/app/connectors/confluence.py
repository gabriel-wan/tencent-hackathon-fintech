"""Confluence connector. API details: docs/connectors/reference/CONFLUENCE.md.

Every call uses one person's own Atlassian sign-in (store.client): the company admin's for sync and
the scope list, the asking user's for the live check.
"""

import html
import re
from collections.abc import Callable, Iterable, Iterator

import httpx

from app.connectors.atlassian import get, links_pages, pages

BLOCK_END = re.compile(r"</(p|h\d|li|tr|div|pre|blockquote)>|<br\s*/?>")
TAG = re.compile(r"<[^>]+>")


def storage_text(storage: str) -> str:
    return html.unescape(TAG.sub("", BLOCK_END.sub("\n", storage))).strip()


def scopes(http: httpx.Client) -> list[dict]:
    """Spaces this person can see, for the admin to choose the boundary from."""
    return [{"id": s["id"], "title": s["name"]} for s in links_pages(http, "/wiki/api/v2/spaces", limit=250)]


def fetch(http: httpx.Client, space: str, changed: Callable[[str, str], bool] = lambda *_: True) -> Iterator[dict]:
    """One document per page (docs/connectors/reference/CONFLUENCE.md section 5); `text` None if not `changed`."""
    groups: dict[str, list[str]] = {}
    readers: dict[str, list[str] | None] = {}  # content id -> its read restriction, None if unrestricted

    def members(group_id: str) -> list[str]:
        if group_id not in groups:
            groups[group_id] = [f"atlassian:user:{u['accountId']}" for u in pages(
                http, f"/wiki/rest/api/group/{group_id}/membersByGroupId", "results", start="start", size="limit")]
        return groups[group_id]

    def restriction(content_id: str) -> list[str] | None:
        if content_id not in readers:
            r = get(http, f"/wiki/rest/api/content/{content_id}/restriction/byOperation/read",
                    expand="restrictions.user,restrictions.group")["restrictions"]
            users = [f"atlassian:user:{u['accountId']}" for u in r["user"]["results"]]
            in_groups = [m for g in r["group"]["results"] for m in members(g["id"])]
            readers[content_id] = sorted(set(users + in_groups)) if users or in_groups else None
        return readers[content_id]

    in_space = list(links_pages(http, f"/wiki/api/v2/spaces/{space}/pages", **{"body-format": "storage", "limit": 250}))
    parent = {p["id"]: p.get("parentId") for p in in_space}
    for page in in_space:
        chain, node = [], page["id"]
        while node in parent:  # the page, then its parents upwards
            chain.append(node)
            node = parent[node]
        # The deepest restriction holds every real reader; unrestricted means everyone in the company
        # who can open the space. Space permissions, and restrictions on a parent that is not
        # a page (e.g. a folder), are not modelled (too wide is allowed; the live check trims).
        acl = next((r for r in map(restriction, chain) if r is not None), ["public"])
        updated_at = page["version"]["createdAt"]
        yield {
            "source": "confluence",
            "source_id": page["id"],
            "scope_id": space,
            "title": page["title"],
            "url": page["_links"]["base"] + page["_links"]["webui"],
            "updated_at": updated_at,
            "acl": acl,
            "text": storage_text(page["body"]["storage"]["value"]) if changed(page["id"], updated_at) else None,
            # Need-to-Know Shield (ADR-010): the page's owner and author see its identifiers unmasked.
            "metadata": {"need_to_know": sorted({f"atlassian:user:{a}"
                                                 for a in (page.get("ownerId"), page.get("authorId")) if a})},
        }


def can_read(http: httpx.Client, ids: Iterable[str]) -> set[str]:
    """Live check (ADR-003): which of these pages the sign-in's owner can read right now (one search)."""
    ids = [i for i in ids if i.isdigit()]
    if not ids:
        return set()
    resp = get(http, "/wiki/rest/api/search", cql=f"id in ({','.join(ids)})", limit=len(ids))
    return {r["content"]["id"] for r in resp["results"] if r.get("content")}

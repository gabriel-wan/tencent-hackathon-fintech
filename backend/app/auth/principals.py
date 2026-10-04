"""Principals: who a user is on each platform, as namespaced strings.

A document is a search candidate only if its ACL shares at least one principal
with the user (see docs/architecture/QUERY_PIPELINE.md).
"""
from sqlalchemy import Connection, text

# Held by everyone: Drive files shared as "anyone with the link".
PUBLIC = "public"

# The principal that identifies the user to each platform's live check.
IDENTITY_PREFIX = {
    "slack": "slack:user:",
    "drive": "google:user:",
    "jira": "atlassian:user:",
    "confluence": "atlassian:user:",
}


def principals_for(conn: Connection, user_id: int) -> list[str]:
    rows = conn.execute(
        text("SELECT principal FROM user_principals WHERE user_id = :u"), {"u": user_id}
    ).scalars().all()
    return sorted(set(rows) | {PUBLIC})


def identity_for(principals: list[str], source: str) -> str | None:
    """The user's own principal on `source`, or None if they have not linked it."""
    prefix = IDENTITY_PREFIX.get(source)
    if prefix is None:
        return None
    matches = sorted(p for p in principals if p.startswith(prefix))
    return matches[0] if matches else None

"""Companies: many companies share one deployment, and each sees only its own data.

A company is created by the first sign-in from a new Slack workspace or Atlassian site, and the
first person to join it becomes its admin. Later sign-ins from that workspace or site join it.
Google names no company: a person who connected only Drive has none (and sees nothing) until they
connect Slack or Atlassian, in any order. An admin connecting an Atlassian site (or Slack
workspace) their company has none of yet adds it.

ponytail: anyone who controls a Slack workspace or Atlassian site can start a company from it;
add an approval step or domain verification when strangers sign up.
"""

from sqlalchemy import Connection, text

from app.db import engine


def _resolve(column: str, value: str, name: str, email: str, create: bool = True) -> int | None:
    """The company owning this workspace/site, created (if `create`) or claimed if nobody owns it yet."""
    with engine.begin() as db:
        owner = db.execute(text(f"SELECT id FROM companies WHERE {column} = :v"), {"v": value}).scalar()
        if owner is not None:
            return owner  # a user already in another company is refused at linking (api._link)
        user = db.execute(text("SELECT company_id, is_admin FROM users WHERE email = :e"), {"e": email}).first()
        if (user is None or user.company_id is None) and create:  # a new company; ON CONFLICT: two first sign-ins at once both join one company
            db.execute(text(f"INSERT INTO companies (name, {column}) VALUES (:n, :v) ON CONFLICT DO NOTHING"),
                       {"n": name, "v": value})
            return db.execute(text(f"SELECT id FROM companies WHERE {column} = :v"), {"v": value}).scalar_one()
        if user is not None and user.is_admin:  # the admin adds their company's (first) workspace or site
            claimed = db.execute(text(f"UPDATE companies SET {column} = :v WHERE id = :c AND {column} IS NULL"),
                                 {"v": value, "c": user.company_id}).rowcount
            return user.company_id if claimed else None
        return None


def for_slack(team_id: str, team_name: str, email: str, create: bool) -> int | None:
    """`create` is False for guests: an outsider must never start (and admin) a company."""
    return _resolve("slack_team_id", team_id, team_name, email, create)


def for_atlassian(sites: list[dict], email: str) -> tuple[int, str] | None:
    """(company, its cloud ID) for the sites this sign-in granted: the one known site, or the only site.
    Several sites and none (or more than one) known: refused, sign in again granting one site."""
    with engine.connect() as db:
        known = db.execute(text("SELECT atlassian_cloud_id FROM companies WHERE atlassian_cloud_id = ANY(:ids)"),
                           {"ids": [s["id"] for s in sites]}).scalars().all()
    # Distinct IDs: Atlassian may list one site twice (an entry with the Jira scopes, one with Confluence's).
    candidates = set(known) or {s["id"] for s in sites}
    if len(candidates) != 1:
        return None
    site = next(s for s in sites if s["id"] in candidates)
    company = _resolve("atlassian_cloud_id", site["id"], site["name"], email)
    return company and (company, site["id"])


def join(db: Connection, user_id: int, company_id: int) -> bool:
    """Put a user who has no company yet into this one, as its admin if it has none (its first member).
    Returns True if they were made admin. ponytail: two first sign-ins at once can both become admin."""
    return db.execute(text("UPDATE users SET company_id = :c, is_admin = NOT EXISTS "
                           "(SELECT 1 FROM users WHERE company_id = :c AND is_admin) "
                           "WHERE id = :u RETURNING is_admin"), {"u": user_id, "c": company_id}).scalar_one()

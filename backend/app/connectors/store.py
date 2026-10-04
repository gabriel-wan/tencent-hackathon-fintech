"""Each user's connections (ADR-002): encrypted tokens, ready-to-use API clients, and the ACL
principals each connection gives its user. Users and sessions are in app/auth/session.py.

Tokens are Fernet-encrypted at rest (TOKEN_ENCRYPTION_KEY). Access tokens are refreshed
automatically when they are about to expire.

Use from any endpoint (engine = `Db` from app.db; pass the engine, not an open
connection, so no connection is held while the API call runs):
    slack_client(engine, user_id).conversations_list()
    drive_service(engine, user_id).files().list().execute()
    with atlassian_client(engine, user_id, "jira") as jira:
        atlassian.request("GET", "/rest/api/3/myself", http=jira)
"""

import logging
import os
import time
from functools import lru_cache

import httpx
import sqlalchemy as sa
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from slack_sdk import WebClient

from app.connectors import atlassian, drive, oauth, slack

log = logging.getLogger(__name__)

REFRESH_MARGIN_S = 60  # refresh a token this long before it expires

# Mirrors migrations/versions/0004_connections.py (user_id references users.id).
connections = sa.Table(
    "connections", sa.MetaData(),
    sa.Column("user_id", sa.BigInteger, primary_key=True),
    sa.Column("provider", sa.String(16), primary_key=True),
    sa.Column("account_id", sa.String(255), nullable=False),
    sa.Column("account_email", sa.String(320), nullable=False),
    sa.Column("account_name", sa.String(255), nullable=False),
    sa.Column("access_token", sa.LargeBinary, nullable=False),
    sa.Column("refresh_token", sa.LargeBinary),
    sa.Column("expires_at", sa.BigInteger),
    sa.Column("scopes", sa.Text, nullable=False),
    sa.Column("extra", sa.JSON, nullable=False),
    sa.Column("updated_at", sa.BigInteger, nullable=False),
    sa.UniqueConstraint("provider", "account_id"),  # an external account belongs to one person
)


class NotConnected(Exception):
    """The user has not connected this provider (or product)."""


class ReconnectNeeded(Exception):
    """The provider no longer accepts the stored grant; the user must connect again."""


@lru_cache
def cipher() -> Fernet:
    # ponytail: one key; use MultiFernet when keys need rotating.
    return Fernet(os.environ["TOKEN_ENCRYPTION_KEY"])


def _encrypt(value: str | None) -> bytes | None:
    return None if value is None else cipher().encrypt(value.encode())


def _decrypt(value: bytes | None) -> str | None:
    return None if value is None else cipher().decrypt(value).decode()


# ---- Connections ----

def principals(provider: str, account: oauth.Account) -> set[str]:
    """The ACL entries this account gives its user (formats: docs/connectors/*.md, section 5).

    Stored in user_principals, which search matches against document ACLs (app/auth/principals.py
    adds "public" for everyone). The live check (can_read) has the final say, so this set may be
    too wide, never too narrow.
    """
    if provider == "slack":
        if account.extra.get("guest") is False:  # unknown = guest; slack.can_read re-checks live
            return {f"slack:user:{account.id}", "slack:members"}
        return {f"slack:user:{account.id}"}
    if provider == "atlassian":
        return {f"atlassian:user:{account.id}"}
    return {f"google:user:{account.email}", f"google:domain:{account.email.split('@')[1]}"}  # verified, lower-case


def _set_principals(db, user_id: int, provider: str, held: set[str]) -> None:
    """Replace the user's principals from this provider (e.g. seeded ones, or a previous account)."""
    db.execute(sa.text("DELETE FROM user_principals WHERE user_id = :u AND principal LIKE :prefix"),
               {"u": user_id, "prefix": f"{provider}:%"})
    if held:
        db.execute(sa.text("INSERT INTO user_principals (user_id, principal) VALUES (:u, :p)"),
                   [{"u": user_id, "p": p} for p in held])


def save_connection(db, user_id: int, provider: str, account: oauth.Account, tokens: oauth.Tokens) -> None:
    values = {
        "account_id": account.id, "account_email": account.email, "account_name": account.name,
        "access_token": _encrypt(tokens.access_token), "refresh_token": _encrypt(tokens.refresh_token),
        "expires_at": tokens.expires_at, "scopes": tokens.scopes, "extra": account.extra,
        "updated_at": int(time.time()),
    }
    key = (connections.c.user_id == user_id) & (connections.c.provider == provider)
    if db.execute(connections.update().where(key).values(**values)).rowcount == 0:
        db.execute(connections.insert().values(user_id=user_id, provider=provider, **values))
    _set_principals(db, user_id, provider, principals(provider, account))


def connection_owner(db, provider: str, account_id: str) -> int | None:
    return db.execute(sa.select(connections.c.user_id).where(
        connections.c.provider == provider, connections.c.account_id == account_id)).scalar()


def list_connections(db, user_id: int) -> dict[str, dict]:
    """provider -> account details. Never includes tokens."""
    cols = [connections.c.provider, connections.c.account_email, connections.c.account_name, connections.c.extra]
    rows = db.execute(sa.select(*cols).where(connections.c.user_id == user_id)).mappings()
    return {r["provider"]: dict(r) for r in rows}


def delete_connection(db, user_id: int, provider: str) -> tuple[str, str | None] | None:
    """Removes the connection and its principals; returns its (access, refresh) tokens for revoking, or None."""
    key = (connections.c.user_id == user_id) & (connections.c.provider == provider)
    row = db.execute(sa.select(connections.c.access_token, connections.c.refresh_token).where(key)).first()
    if row is None:
        return None
    db.execute(connections.delete().where(key))
    _set_principals(db, user_id, provider, set())
    return _decrypt(row.access_token), _decrypt(row.refresh_token)


def access_token(engine: sa.Engine, user_id: int, provider: str) -> tuple[str, dict]:
    """A valid access token for this user and provider (refreshed if needed), plus `extra`."""
    key = (connections.c.user_id == user_id) & (connections.c.provider == provider)
    # Own transaction, committed here: a refreshed token must survive even if the request fails
    # afterwards, because Atlassian refresh tokens are single-use (the old one is already spent).
    with engine.begin() as tx:
        # Row lock, held during the refresh call: concurrent requests by the same user must not both
        # spend the same refresh token. They wait at most one refresh (oauth timeout).
        row = tx.execute(sa.select(connections).where(key).with_for_update()).mappings().first()
        if row is None:
            raise NotConnected(provider)
        if row["expires_at"] is None or row["expires_at"] - REFRESH_MARGIN_S > time.time():
            return _decrypt(row["access_token"]), row["extra"]
        refresh_token = _decrypt(row["refresh_token"])
        if refresh_token is None:
            raise ReconnectNeeded(provider)
        try:
            tokens = oauth.refresh(provider, refresh_token)
        except oauth.OAuthError as e:
            if e.status >= 500:  # provider trouble: the grant may still be fine, try again later
                raise
            log.warning("Token refresh rejected for %s: %s", provider, e)
            raise ReconnectNeeded(provider) from e
        tx.execute(connections.update().where(key).values(
            access_token=_encrypt(tokens.access_token),
            refresh_token=_encrypt(tokens.refresh_token or refresh_token),  # Google keeps the old one
            expires_at=tokens.expires_at, updated_at=int(time.time()),
        ))
    return tokens.access_token, row["extra"]


# ---- API clients acting as the user ----

def slack_client(engine: sa.Engine, user_id: int) -> WebClient:
    return slack.client(access_token(engine, user_id, "slack")[0])


def google_credentials(engine: sa.Engine, user_id: int) -> Credentials:
    """For drive.service() or drive.can_read() as this user."""
    return Credentials(access_token(engine, user_id, "google")[0])


def drive_service(engine: sa.Engine, user_id: int):
    return drive.service(google_credentials(engine, user_id))


def atlassian_site(extra: dict, product: str) -> dict | None:
    """First granted site that includes `product` ("jira" or "confluence")."""
    return next((s for s in extra.get("sites", []) if any(product in scope for scope in s["scopes"])), None)


def atlassian_client(engine: sa.Engine, user_id: int, product: str) -> httpx.Client:
    # ponytail: first matching site; let the user pick a site if anyone connects several.
    token, extra = access_token(engine, user_id, "atlassian")
    site = atlassian_site(extra, product)
    if site is None:
        raise NotConnected(product)
    return atlassian.user_client(token, product, site["id"])

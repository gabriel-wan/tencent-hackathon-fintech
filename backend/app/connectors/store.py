"""Each user's connections (ADR-002): encrypted tokens, ready-to-use API clients, and the ACL
principals a user holds. Users and sessions are in app/auth.py.

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
import uuid
from functools import lru_cache

import httpx
import sqlalchemy as sa
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from slack_sdk import WebClient

from app import auth
from app.connectors import atlassian, drive, oauth, slack
from app.db import metadata

log = logging.getLogger(__name__)

REFRESH_MARGIN_S = 60  # refresh a token this long before it expires

# Mirrors migrations/versions/0002_connections.py.
connections = sa.Table(
    "connections", metadata,
    sa.Column("user_id", sa.Uuid, sa.ForeignKey(auth.users.c.id, ondelete="CASCADE"), primary_key=True),
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

def save_connection(db, user_id: uuid.UUID, provider: str, account: oauth.Account, tokens: oauth.Tokens) -> None:
    values = {
        "account_id": account.id, "account_email": account.email, "account_name": account.name,
        "access_token": _encrypt(tokens.access_token), "refresh_token": _encrypt(tokens.refresh_token),
        "expires_at": tokens.expires_at, "scopes": tokens.scopes, "extra": account.extra,
        "updated_at": int(time.time()),
    }
    key = (connections.c.user_id == user_id) & (connections.c.provider == provider)
    if db.execute(connections.update().where(key).values(**values)).rowcount == 0:
        db.execute(connections.insert().values(user_id=user_id, provider=provider, **values))


def connection_owner(db, provider: str, account_id: str) -> uuid.UUID | None:
    return db.execute(sa.select(connections.c.user_id).where(
        connections.c.provider == provider, connections.c.account_id == account_id)).scalar()


def list_connections(db, user_id: uuid.UUID) -> dict[str, dict]:
    """provider -> account details. Never includes tokens."""
    cols = [connections.c.provider, connections.c.account_email, connections.c.account_name, connections.c.extra]
    rows = db.execute(sa.select(*cols).where(connections.c.user_id == user_id)).mappings()
    return {r["provider"]: dict(r) for r in rows}


def principals(db, user_id: uuid.UUID) -> set[str]:
    """The ACL entries this user holds (formats: docs/connectors/*.md, section 5).

    Search keeps a document if its `acl` shares one of these (Postgres: `acl && :principals`);
    the live check (can_read) has the final say. So this set may be too wide, never too narrow.
    """
    rows = db.execute(sa.select(connections.c.provider, connections.c.account_id, connections.c.account_email)
                      .where(connections.c.user_id == user_id))
    held = set()
    for provider, account_id, email in rows:
        if provider == "slack":
            held |= {f"slack:user:{account_id}", "slack:members"}  # guests too: slack.can_read drops them
        elif provider == "atlassian":
            held.add(f"atlassian:user:{account_id}")
        elif provider == "google":  # email is verified and lower-cased at sign-in
            held |= {f"google:user:{email}", f"google:domain:{email.split('@')[1]}", "public"}
    return held


def delete_connection(db, user_id: uuid.UUID, provider: str) -> tuple[str, str | None] | None:
    """Removes the connection; returns its (access, refresh) tokens for revoking, or None."""
    key = (connections.c.user_id == user_id) & (connections.c.provider == provider)
    row = db.execute(sa.select(connections.c.access_token, connections.c.refresh_token).where(key)).first()
    if row is None:
        return None
    db.execute(connections.delete().where(key))
    return _decrypt(row.access_token), _decrypt(row.refresh_token)


def access_token(engine: sa.Engine, user_id: uuid.UUID, provider: str) -> tuple[str, dict]:
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

def slack_client(engine: sa.Engine, user_id: uuid.UUID) -> WebClient:
    return slack.client(access_token(engine, user_id, "slack")[0])


def google_credentials(engine: sa.Engine, user_id: uuid.UUID) -> Credentials:
    """For drive.service() or drive.can_read() as this user."""
    return Credentials(access_token(engine, user_id, "google")[0])


def drive_service(engine: sa.Engine, user_id: uuid.UUID):
    return drive.service(google_credentials(engine, user_id))


def atlassian_site(extra: dict, product: str) -> dict | None:
    """First granted site that includes `product` ("jira" or "confluence")."""
    return next((s for s in extra.get("sites", []) if any(product in scope for scope in s["scopes"])), None)


def atlassian_client(engine: sa.Engine, user_id: uuid.UUID, product: str) -> httpx.Client:
    # ponytail: first matching site; let the user pick a site if anyone connects several.
    token, extra = access_token(engine, user_id, "atlassian")
    site = atlassian_site(extra, product)
    if site is None:
        raise NotConnected(product)
    return atlassian.user_client(token, product, site["id"])

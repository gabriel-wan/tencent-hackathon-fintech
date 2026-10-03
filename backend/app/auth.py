"""Who is asking (ADR-002): app users and their sessions.

There is no separate login: signing in to the first connector creates the user and the session
(app/connectors/api.py). A user is one company email; the session cookie holds a random token and
only its sha256 is stored.

In any endpoint:  def handler(user: User, engine: Db): ...   (401 if not signed in)
"""

import hashlib
import os
import secrets
import time
import uuid
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.db import Db, metadata

router = APIRouter()

SESSION_COOKIE = "session"
SESSION_TTL_S = 7 * 24 * 3600

users = sa.Table(
    "users", metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("email", sa.String(320), nullable=False, unique=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
)
sessions = sa.Table(
    "sessions", metadata,
    sa.Column("token_hash", sa.String(64), primary_key=True),
    sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    sa.Column("expires_at", sa.BigInteger, nullable=False),
)

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def secure_cookies() -> bool:
    # APP_URL is required (no default): it decides whether cookies are Secure (https only).
    return os.environ["APP_URL"].startswith("https://")


# ---- Users and sessions ----

def find_user(db, email: str) -> uuid.UUID | None:
    return db.execute(sa.select(users.c.id).where(users.c.email == email.lower())).scalar()


def create_user(db, email: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    db.execute(users.insert().values(id=user_id, email=email.lower()))
    return user_id


def create_session(db, user_id: uuid.UUID) -> str:
    """Returns the cookie value; only its hash is stored."""
    token = secrets.token_urlsafe(32)
    db.execute(sessions.insert().values(token_hash=_hash(token), user_id=user_id,
                                        expires_at=int(time.time()) + SESSION_TTL_S))
    return token


def session_user(db, token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    return db.execute(sa.select(sessions.c.user_id).where(
        sessions.c.token_hash == _hash(token), sessions.c.expires_at > int(time.time()))).scalar()


def delete_session(db, token: str) -> None:
    db.execute(sessions.delete().where(sessions.c.token_hash == _hash(token)))


def set_session_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL_S,
                    httponly=True, samesite="lax", secure=secure_cookies(), path="/")


# ---- FastAPI dependencies ----

def current_user(request: Request, engine: Db) -> uuid.UUID | None:
    with engine.connect() as db:
        return session_user(db, request.cookies.get(SESSION_COOKIE))


MaybeUser = Annotated[uuid.UUID | None, Depends(current_user)]


def require_user(user: MaybeUser) -> uuid.UUID:
    if user is None:
        raise HTTPException(401, "not signed in: connect a connector first")
    return user


User = Annotated[uuid.UUID, Depends(require_user)]


@router.post("/logout", status_code=204)
def logout(request: Request, engine: Db):
    if token := request.cookies.get(SESSION_COOKIE):
        with engine.begin() as db:
            delete_session(db, token)
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp

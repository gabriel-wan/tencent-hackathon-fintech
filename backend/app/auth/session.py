"""Server-side sessions (ADR-002).

The browser holds a random token in an httpOnly cookie; the database stores
only its SHA-256. The signed-in user always comes from here, never from a user
ID sent by the browser (SECURITY.md INV-3).
"""
import hashlib
import secrets
from dataclasses import dataclass

from sqlalchemy import Connection, text

COOKIE_NAME = "ib_session"
SESSION_HOURS = 12


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    is_admin: bool
    company_id: int | None  # their company (app/companies.py); None until a connection names one: sees nothing


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn: Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        text(
            "INSERT INTO sessions (token_hash, user_id, expires_at) "
            "VALUES (:token_hash, :user_id, now() + make_interval(hours => :hours))"
        ),
        {"token_hash": _hash(token), "user_id": user_id, "hours": SESSION_HOURS},
    )
    return token


def delete_session(conn: Connection, token: str) -> None:
    conn.execute(text("DELETE FROM sessions WHERE token_hash = :h"), {"h": _hash(token)})


def user_for_token(conn: Connection, token: str) -> User | None:
    row = conn.execute(
        text(
            "SELECT u.id, u.email, u.name, u.is_admin, u.company_id FROM sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = :h AND s.expires_at > now()"
        ),
        {"h": _hash(token)},
    ).first()
    return User(*row) if row else None  # columns selected in User's field order


def get_user(conn: Connection, user_id: int) -> User | None:
    row = conn.execute(
        text("SELECT id, email, name, is_admin, company_id FROM users WHERE id = :id"), {"id": user_id}
    ).first()
    return User(*row) if row else None  # columns selected in User's field order


# Connector sign-in (app/connectors/api.py): a user is one company email (ADR-002).

def get_user_by_email(conn: Connection, email: str) -> User | None:
    row = conn.execute(
        text("SELECT id, email, name, is_admin, company_id FROM users WHERE email = :e"), {"e": email.lower()}
    ).first()
    return User(*row) if row else None  # columns selected in User's field order


def create_user(conn: Connection, email: str, name: str, company_id: int | None) -> User:
    user_id = conn.execute(
        text("INSERT INTO users (email, name, company_id) VALUES (:e, :n, :c) RETURNING id"),
        {"e": email.lower(), "n": name, "c": company_id},
    ).scalar_one()
    return User(user_id, email.lower(), name, False, company_id)

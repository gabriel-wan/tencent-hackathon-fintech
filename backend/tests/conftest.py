"""Test setup: a separate *_test database, migrated once, one rolled-back transaction per test."""
import os
from collections.abc import Sequence

import httpx
import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text

DB_NAME = os.environ.get("POSTGRES_DB", "")
if not DB_NAME.endswith("_test"):
    pytest.exit(
        f"Refusing to run tests against database {DB_NAME!r}: POSTGRES_DB must end with '_test'. "
        "See docs/DEVELOPMENT.md section 3.",
        returncode=2,
    )

from app.auth.session import User  # noqa: E402  (after the safety check)
from app.connectors import atlassian, slack, store  # noqa: E402
from app.db import engine  # noqa: E402
from app.retrieval.search import vector_literal  # noqa: E402
from tests.helpers import FakeLLM  # noqa: E402


def _create_test_database() -> None:
    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname="postgres",
        autocommit=True,
    ) as admin:
        if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)).fetchone():
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    from alembic import command
    from alembic.config import Config

    _create_test_database()
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def conn():
    """Each test runs inside one transaction that is rolled back afterwards."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def make_user(conn):
    def _make(email: str, principals: Sequence[str], is_admin: bool = False, name: str = "") -> User:
        user_id = conn.execute(
            text("INSERT INTO users (email, name, is_admin) VALUES (:e, :n, :a) RETURNING id"),
            {"e": email, "n": name or email, "a": is_admin},
        ).scalar_one()
        for p in principals:
            conn.execute(text("INSERT INTO user_principals VALUES (:u, :p)"), {"u": user_id, "p": p})
        return User(user_id, email, name or email, is_admin)

    return _make


@pytest.fixture
def add_doc(conn):
    def _add(
        source: str,
        source_id: str,
        acl: Sequence[str],
        body: str,
        scope_id: str = "SCOPE1",
        in_boundary: bool = True,
        embedding: Sequence[float] | None = None,
        deleted: bool = False,
        title: str = "",
    ) -> int:
        if in_boundary:
            conn.execute(
                text(
                    "INSERT INTO boundary (source, scope_id, scope_type) VALUES (:s, :i, :t) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"s": source, "i": scope_id, "t": "channel" if source == "slack" else "folder"},
            )
        doc_id = conn.execute(
            text(
                "INSERT INTO documents (source, source_id, scope_id, title, url, updated_at, acl, deleted_at) "
                "VALUES (:s, :sid, :scope, :t, :url, now(), CAST(:acl AS text[]), "
                "CASE WHEN :deleted THEN now() END) RETURNING id"
            ),
            {"s": source, "sid": source_id, "scope": scope_id, "t": title or source_id,
             "url": f"https://example.test/{source_id}", "acl": list(acl), "deleted": deleted},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO chunks (document_id, ordinal, text, embedding) "
                "VALUES (:d, 0, :t, CAST(:v AS vector))"
            ),
            {"d": doc_id, "t": body, "v": vector_literal(embedding) if embedding is not None else None},
        )
        return doc_id

    return _add


@pytest.fixture
def fake_llm():
    return FakeLLM


# ---- Connectors (Task 1): no test reaches a real provider API ----

@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    """Tests never reach real APIs: drop connector env vars and any cached client or key."""
    for key in list(os.environ):
        if key.startswith(("ATLASSIAN_", "GOOGLE_", "SLACK_", "APP_URL", "FRONTEND_URL", "TOKEN_ENCRYPTION_KEY")):
            monkeypatch.delenv(key)
    atlassian.client.cache_clear()
    slack.bot.cache_clear()
    store.cipher.cache_clear()


@pytest.fixture
def atlassian_api(monkeypatch):
    """install(handler) routes Atlassian calls to handler(request) -> Response; returns (sent, sleeps)."""
    sent, sleeps = [], []

    def install(handler):
        def record(request):
            sent.append(request)
            return handler(request)

        c = httpx.Client(base_url="https://example.atlassian.net", transport=httpx.MockTransport(record))
        monkeypatch.setattr(atlassian, "client", lambda: c)
        monkeypatch.setattr(atlassian.time, "sleep", sleeps.append)
        return sent, sleeps

    return install

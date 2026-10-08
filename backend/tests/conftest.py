"""Test setup: a separate *_test database, migrated once, one rolled-back transaction per test."""
import json
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
        "See docs/TESTING.md section 1.",
        returncode=2,
    )

from app.auth.session import User  # noqa: E402  (after the safety check)
from app.connectors import atlassian, store  # noqa: E402
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
def make_company(conn):
    def _make(name: str = "Acme") -> int:
        return conn.execute(text("INSERT INTO companies (name) VALUES (:n) RETURNING id"), {"n": name}).scalar_one()

    return _make


@pytest.fixture
def company(make_company):
    """The company that make_user and add_doc use unless told otherwise."""
    return make_company()


@pytest.fixture
def make_user(conn, company):
    def _make(email: str, principals: Sequence[str], is_admin: bool = False, name: str = "",
              company_id: int | None = None) -> User:
        company_id = company_id or company
        user_id = conn.execute(
            text("INSERT INTO users (email, name, is_admin, company_id) VALUES (:e, :n, :a, :c) RETURNING id"),
            {"e": email, "n": name or email, "a": is_admin, "c": company_id},
        ).scalar_one()
        for p in principals:
            conn.execute(text("INSERT INTO user_principals VALUES (:u, :p)"), {"u": user_id, "p": p})
        return User(user_id, email, name or email, is_admin, company_id)

    return _make


@pytest.fixture
def add_doc(conn, company):
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
        company_id: int | None = None,
        metadata: dict | None = None,
    ) -> int:
        company_id = company_id or company
        if in_boundary:
            conn.execute(
                text(
                    "INSERT INTO boundary (company_id, source, scope_id, scope_type) VALUES (:c, :s, :i, :t) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"c": company_id, "s": source, "i": scope_id, "t": "channel" if source == "slack" else "folder"},
            )
        doc_id = conn.execute(
            text(
                "INSERT INTO documents (company_id, source, source_id, scope_id, title, url, updated_at, acl, "
                "deleted_at, metadata) VALUES (:c, :s, :sid, :scope, :t, :url, now(), CAST(:acl AS text[]), "
                "CASE WHEN :deleted THEN now() END, CAST(:meta AS jsonb)) RETURNING id"
            ),
            {"c": company_id, "s": source, "sid": source_id, "scope": scope_id, "t": title or source_id,
             "url": f"https://example.test/{source_id}", "acl": list(acl), "deleted": deleted,
             "meta": json.dumps(metadata or {})},
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
    store.cipher.cache_clear()


@pytest.fixture
def atlassian_api(monkeypatch):
    """install(handler) -> (http, sent, sleeps): a client whose calls go to handler(request) -> Response."""
    sent, sleeps = [], []

    def install(handler):
        def record(request):
            sent.append(request)
            return handler(request)

        monkeypatch.setattr(atlassian.time, "sleep", sleeps.append)
        return httpx.Client(base_url="https://example.atlassian.net", transport=httpx.MockTransport(record)), sent, sleeps

    return install

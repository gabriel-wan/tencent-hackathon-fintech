"""Company admin API: admins only, only their own company, every boundary change audited."""

import pytest
from fastapi.testclient import TestClient
from slack_sdk.errors import SlackApiError
from sqlalchemy import text

from app import sync
from app.connectors import store
from app.db import engine
from app.main import create_app


def empty():
    with engine.begin() as c:
        c.execute(text("TRUNCATE companies, users CASCADE"))


def add(conn, sql, **params):
    return conn.execute(text(sql + " RETURNING id"), params).scalar()


@pytest.fixture
def db():
    """Two companies; Acme has an admin and a member, and a synced document in channel C1."""
    empty()
    with engine.begin() as c:
        acme, other = (add(c, "INSERT INTO companies (name) VALUES (:n)", n=n) for n in ("Acme", "Other"))
        ids = {
            "admin": add(c, "INSERT INTO users (email, is_admin, company_id) VALUES ('a@acme.example', true, :c)", c=acme),
            "member": add(c, "INSERT INTO users (email, company_id) VALUES ('m@acme.example', :c)", c=acme),
            "acme": acme, "other": other,
        }
        for company in (acme, other):
            c.execute(text("INSERT INTO boundary (company_id, source, scope_id, scope_type) "
                           "VALUES (:c, 'slack', 'C1', 'channel')"), {"c": company})
            add(c, "INSERT INTO documents (company_id, source, source_id, scope_id, updated_at) "
                   "VALUES (:c, 'slack', 'C1:1', 'C1', now())", c=company)
    yield ids
    empty()


def signed_in(user_id):
    client = TestClient(create_app("development"))
    client.post("/api/dev/session", json={"user_id": user_id})
    return client


def rows(sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).all()


def test_members_are_refused(db):
    member = signed_in(db["member"])
    assert member.get("/api/admin/boundary").status_code == 403
    assert member.put("/api/admin/boundary/slack/C2", json={"title": "#x"}).status_code == 403
    assert member.post("/api/admin/sync").status_code == 403


def test_boundary_changes_touch_only_the_admins_company_and_are_audited(db):
    admin = signed_in(db["admin"])
    assert admin.put("/api/admin/boundary/slack/C2", json={"title": "#payments"}).status_code == 204
    assert admin.delete("/api/admin/boundary/slack/C1").status_code == 204

    assert [b["scope_id"] for b in admin.get("/api/admin/boundary").json()] == ["C2"]
    assert rows("SELECT company_id, scope_id FROM boundary ORDER BY company_id, scope_id") == [
        (db["acme"], "C2"), (db["other"], "C1")]  # the other company's C1 is untouched
    assert rows("SELECT company_id, deleted_at IS NOT NULL FROM documents ORDER BY company_id") == [
        (db["acme"], True), (db["other"], False)]  # removing a scope hides its documents
    assert [r[0] for r in rows("SELECT event_type FROM audit_events WHERE user_id = :u ORDER BY id", u=db["admin"])] \
        == ["boundary_added", "boundary_removed"]


def test_boundary_shows_when_each_scope_last_synced(db):
    admin = signed_in(db["admin"])
    assert admin.get("/api/admin/boundary").json()[0]["last_synced_at"] is None  # never synced
    with engine.begin() as c:
        c.execute(text("INSERT INTO sync_state (company_id, source, key) VALUES (:c, 'slack', 'C1')"),
                  {"c": db["acme"]})
    assert admin.get("/api/admin/boundary").json()[0]["last_synced_at"] is not None
    assert admin.delete("/api/admin/boundary/slack/C1").status_code == 204
    assert rows("SELECT company_id FROM sync_state") == []  # re-adding the scope starts as never synced


def test_unknown_source_or_odd_scope_id_is_rejected(db):
    admin = signed_in(db["admin"])
    assert admin.put("/api/admin/boundary/teams/X", json={}).status_code == 404
    assert admin.put('/api/admin/boundary/jira/PAY" OR project = "HR', json={}).status_code == 422  # never in JQL


def test_scopes_need_the_admins_own_connection(db):
    assert signed_in(db["admin"]).get("/api/admin/scopes/slack").status_code == 404  # not connected yet


def test_scopes_with_a_revoked_token_ask_to_connect_again(db, monkeypatch):
    class Slack:
        def conversations_list(self, **_):
            raise SlackApiError("token_revoked", {"ok": False, "error": "token_revoked"})

    monkeypatch.setattr(store, "client", lambda *_: Slack())
    resp = signed_in(db["admin"]).get("/api/admin/scopes/slack")
    assert resp.status_code == 401 and "connect again" in resp.json()["detail"]  # not a 500


def test_sync_now_syncs_the_admins_company(db, monkeypatch):
    calls = []
    monkeypatch.setattr(sync, "sync_company", lambda _engine, company: calls.append(company))
    assert signed_in(db["admin"]).post("/api/admin/sync").status_code == 202
    assert calls == [db["acme"]]
    assert rows("SELECT event_type FROM audit_events WHERE user_id = :u", u=db["admin"]) == [("sync_requested",)]

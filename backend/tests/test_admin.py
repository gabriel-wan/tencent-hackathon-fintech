"""Company admin API: admins only, only their own company, every boundary change audited."""

import pytest
from fastapi.testclient import TestClient
from slack_sdk.errors import SlackApiError
from sqlalchemy import text

from app import sync
from app.connectors import store
from app.db import engine, owner_engine
from app.main import create_app


def empty():
    with owner_engine().begin() as c:  # the app may not empty tables
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


class Tree:
    """Drive's files().get for parents: Finance > 2026 > Payroll."""

    PARENT = {"PAY": "Y26", "Y26": "FIN", "FIN": None, "ENG": None}

    def files(self):
        return self

    def get(self, fileId, **_):
        parent = self.PARENT[fileId]

        class Call:
            def execute(self, **_):
                return {"parents": [parent]} if parent else {}
        return Call()


def drive_scope(db, folder, title):
    with engine.begin() as c:
        c.execute(text("INSERT INTO boundary (company_id, source, scope_id, scope_type, title) "
                       "VALUES (:c, 'drive', :i, 'folder', :t)"), {"c": db["acme"], "i": folder, "t": title})


def test_a_drive_folder_overlapping_one_in_the_boundary_is_refused(db, monkeypatch):
    monkeypatch.setattr(store, "client", lambda *_: Tree())
    admin = signed_in(db["admin"])
    drive_scope(db, "Y26", "2026")
    inside = admin.put("/api/admin/boundary/drive/PAY", json={"title": "Payroll"})
    assert inside.status_code == 409 and inside.json()["detail"] == \
        "Payroll is inside 2026, which is already in the boundary"
    above = admin.put("/api/admin/boundary/drive/FIN", json={"title": "Finance"})
    assert above.status_code == 409 and "Finance contains 2026" in above.json()["detail"]
    assert admin.put("/api/admin/boundary/drive/ENG", json={"title": "Eng"}).status_code == 204  # unrelated
    assert admin.put("/api/admin/boundary/drive/Y26", json={"title": "2026"}).status_code == 204  # re-adding
    assert sorted(r[0] for r in rows("SELECT scope_id FROM boundary WHERE source = 'drive'")) == ["ENG", "Y26"]


def test_bulk_changes_are_all_or_nothing_and_audited_one_by_one(db):
    admin = signed_in(db["admin"])
    resp = admin.post("/api/admin/boundary/slack/bulk",
                      json={"add": [{"scope_id": "C2", "title": "#a"}, {"scope_id": "C3", "title": "#b"}],
                            "remove": ["C1"]})
    assert resp.status_code == 200 and resp.json() == {"added": 2, "removed": 1}
    assert [r[0] for r in rows("SELECT scope_id FROM boundary WHERE company_id = :c ORDER BY scope_id",
                               c=db["acme"])] == ["C2", "C3"]
    assert rows("SELECT deleted_at IS NOT NULL FROM documents WHERE company_id = :c", c=db["acme"]) == [(True,)]
    assert [r[0] for r in rows("SELECT event_type FROM audit_events WHERE user_id = :u ORDER BY id",
                               u=db["admin"])] == ["boundary_removed", "boundary_added", "boundary_added"]
    assert rows("SELECT scope_id FROM boundary WHERE company_id = :c", c=db["other"]) == [("C1",)]  # untouched


def test_bulk_is_capped_checked_and_admin_only(db, monkeypatch):
    admin = signed_in(db["admin"])
    too_many = [{"scope_id": f"C{i}"} for i in range(51)]
    assert admin.post("/api/admin/boundary/slack/bulk", json={"add": too_many}).status_code == 422
    assert admin.post("/api/admin/boundary/slack/bulk", json={}).status_code == 422
    assert admin.post("/api/admin/boundary/slack/bulk",
                      json={"add": [{"scope_id": "C1"}], "remove": ["C1"]}).status_code == 422
    assert admin.post("/api/admin/boundary/jira/bulk",
                      json={"add": [{"scope_id": 'PAY" OR project = "HR'}]}).status_code == 422  # never in JQL
    assert signed_in(db["member"]).post("/api/admin/boundary/slack/bulk",
                                        json={"add": [{"scope_id": "C2"}]}).status_code == 403
    monkeypatch.setattr(store, "client", lambda *_: Tree())
    nested = admin.post("/api/admin/boundary/drive/bulk",
                        json={"add": [{"scope_id": "FIN", "title": "Finance"}, {"scope_id": "PAY", "title": "Payroll"}]})
    assert nested.status_code == 409  # two overlapping folders in one request
    assert rows("SELECT scope_id FROM boundary WHERE source = 'drive'") == []  # nothing written


def test_removing_a_scope_that_is_not_there_writes_no_audit_event(db):
    admin = signed_in(db["admin"])
    events = lambda: [r[0] for r in rows("SELECT event_type FROM audit_events WHERE user_id = :u ORDER BY id",  # noqa: E731
                                         u=db["admin"])]
    assert admin.delete("/api/admin/boundary/slack/C1").status_code == 204
    assert admin.delete("/api/admin/boundary/slack/C1").status_code == 204  # again: nothing left to remove
    assert events() == ["boundary_removed"]
    resp = admin.post("/api/admin/boundary/slack/bulk", json={"remove": ["C1", "C9"]})  # neither is in
    assert resp.json() == {"added": 0, "removed": 0} and events() == ["boundary_removed"]



def test_re_adding_a_scope_that_is_already_there_writes_no_audit_event(db):
    admin = signed_in(db["admin"])
    events = lambda: [r[0] for r in rows("SELECT event_type FROM audit_events WHERE user_id = :u ORDER BY id",  # noqa: E731
                                         u=db["admin"])]
    assert admin.put("/api/admin/boundary/slack/C1", json={"title": "#renamed"}).status_code == 204  # already in
    assert events() == []
    assert rows("SELECT title FROM boundary WHERE company_id = :c", c=db["acme"]) == [("#renamed",)]  # title kept fresh
    resp = admin.post("/api/admin/boundary/slack/bulk",
                      json={"add": [{"scope_id": "C1", "title": "#renamed"}, {"scope_id": "C2", "title": "#new"}]})
    assert resp.json() == {"added": 1, "removed": 0} and events() == ["boundary_added"]



def test_the_boundary_lock_takes_company_ids_past_32_bits():
    from types import SimpleNamespace
    from app.connectors.admin import _lock

    with engine.begin() as c:
        _lock(c, SimpleNamespace(company_id=3_000_000_000))  # would be "integer out of range" unfolded


class RateLimited(Tree):
    """Drive answering 403 (rate limit) for one parent."""

    def get(self, fileId, **_):
        if fileId == "Y26":
            from googleapiclient.errors import HttpError
            import httplib2

            raise HttpError(httplib2.Response({"status": 403}), b'{"error": {"message": "Rate Limit Exceeded"}}')
        return super().get(fileId)


def test_a_rate_limit_refuses_the_folder_instead_of_skipping_the_check(db, monkeypatch):
    monkeypatch.setattr(store, "client", lambda *_: RateLimited())
    drive_scope(db, "FIN", "Finance")
    resp = signed_in(db["admin"]).put("/api/admin/boundary/drive/PAY", json={"title": "Payroll"})
    assert resp.status_code == 502 and resp.json()["detail"] == "drive API call failed"  # never added unchecked
    assert rows("SELECT scope_id FROM boundary WHERE source = 'drive'") == [("FIN",)]

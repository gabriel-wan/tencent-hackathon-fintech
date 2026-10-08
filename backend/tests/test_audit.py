"""Tamper-evident audit log (ADR-007, SECURITY.md INV-6, INV-7): per-company hash chains, an app role
that can only add records, and the admin's search and verify API."""
import os
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.api.deps import get_conn, get_llm, get_tx
from app.audit.log import record_event, verify_chain
from app.db import APP_ROLE, engine, owner_engine
from app.main import create_app
from tests.helpers import within

OWNER = os.environ["POSTGRES_USER"]


@pytest.fixture
def owner():
    """A connection as the database owner, who can switch the triggers off; rolled back afterwards."""
    with owner_engine().connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def owner_user(owner):
    """(company id, user id), created on the owner's connection."""
    company = owner.execute(text("INSERT INTO companies (name) VALUES ('Acme') RETURNING id")).scalar_one()
    user = owner.execute(text("INSERT INTO users (email, company_id) VALUES ('alice@co.example', :c) RETURNING id"),
                         {"c": company}).scalar_one()
    return company, user


def tamper(owner, sql, **params):
    """What someone with full database access could do: switch the trigger off and change the log."""
    owner.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update_delete"))
    owner.execute(text(sql), params)


def chain(conn, company_id):
    return conn.execute(text("SELECT id, prev_hash, hash FROM audit_events WHERE company_id = :c ORDER BY id"),
                        {"c": company_id}).all()


def query_event(conn, user, *documents, denied=(), restricted=()):
    """A query record shaped like app/pipeline/query.py's."""
    return record_event(conn, user.id, "query", {
        "question": "q",
        "candidates": [{"document": d, "allowed": True, "reason": "ok"} for d in documents]
                      + [{"document": d, "allowed": False, "reason": "denied by live check"} for d in denied],
        "sent_to_llm": list(documents),
        "citations": list(documents),
        "restricted_matches": [{"document": d, "reason": "user not in document ACL"} for d in restricted],
    })


# ---- The chain ----

@pytest.mark.security
def test_each_company_has_its_own_chain(conn, make_company, make_user):
    acme, other = make_company("Acme"), make_company("Other")
    alice = make_user("alice@acme.example", [], company_id=acme)
    olga = make_user("olga@other.example", [], company_id=other)
    for user in (alice, olga, alice, olga, alice):  # interleaved
        record_event(conn, user.id, "query", {"question": "q"})

    for company in (acme, other):
        links = chain(conn, company)
        assert links[0].prev_hash is None  # each chain starts fresh
        assert [r.prev_hash for r in links[1:]] == [r.hash for r in links[:-1]]  # linked within the company only
        assert verify_chain(conn, company)["ok"]
    assert verify_chain(conn, acme)["checked"] == 3


@pytest.mark.security
def test_a_record_without_a_company_goes_in_the_no_company_chain(conn, make_user):
    event = record_event(conn, None, "connector_connected", {"provider": "google"})
    assert conn.execute(text("SELECT company_id FROM audit_events WHERE id = :i"), {"i": event}).scalar() is None
    assert verify_chain(conn, None)["ok"]


@pytest.mark.security
def test_a_changed_record_is_detected(owner, owner_user):
    company, alice = owner_user
    ids = [record_event(owner, alice, "query", {"question": f"q{i}"}) for i in range(3)]
    assert verify_chain(owner, company)["ok"]

    tamper(owner, "UPDATE audit_events SET payload = '{\"question\": \"nothing to see\"}' WHERE id = :i", i=ids[1])
    result = verify_chain(owner, company)
    assert (result["ok"], result["first_broken_id"]) == (False, ids[1])
    assert result["reason"] == "this record was changed after it was written"


@pytest.mark.security
def test_a_deleted_record_is_detected(owner, owner_user):
    company, alice = owner_user
    ids = [record_event(owner, alice, "query", {"question": f"q{i}"}) for i in range(3)]

    tamper(owner, "DELETE FROM audit_events WHERE id = :i", i=ids[1])
    result = verify_chain(owner, company)
    assert (result["ok"], result["first_broken_id"]) == (False, ids[2])  # the next record's link breaks
    assert result["reason"] == "the record before this one was changed, deleted or reordered"


@pytest.mark.security
def test_recomputing_a_changed_records_hash_still_breaks_the_next_link(owner, owner_user):
    company, alice = owner_user
    ids = [record_event(owner, alice, "query", {"question": f"q{i}"}) for i in range(3)]

    tamper(owner, "UPDATE audit_events SET payload = '{}', "
                  "hash = audit_event_hash(prev_hash, id, ts, company_id, user_id, event_type, '{}') WHERE id = :i",
           i=ids[1])
    assert verify_chain(owner, company)["first_broken_id"] == ids[2]


@pytest.mark.security
def test_the_app_role_can_add_records_but_never_change_them_or_switch_the_triggers_off(conn, make_user):
    alice = make_user("alice@co.example", [])
    event = record_event(conn, alice.id, "query", {"question": "q"})  # the app role can add
    for statement in ("UPDATE audit_events SET payload = '{}' WHERE id = :i",
                      "DELETE FROM audit_events WHERE id = :i",
                      "TRUNCATE audit_events",
                      "TRUNCATE users CASCADE",  # the app never empties tables
                      "ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update_delete"):
        savepoint = conn.begin_nested()
        with pytest.raises(DBAPIError, match="permission denied|must be owner"):
            conn.execute(text(statement), {"i": event})
        savepoint.rollback()


@pytest.mark.security
def test_the_app_can_never_switch_to_a_more_powerful_role(conn):
    """Review of PR #11: the app used to log in as the owner, and `SET ROLE NONE` switched back to it."""
    conn.execute(text("SET ROLE NONE"))
    assert conn.execute(text("SELECT current_user, session_user")).one() == (APP_ROLE, APP_ROLE)
    assert conn.execute(text("SELECT rolsuper OR rolcreaterole OR rolbypassrls FROM pg_roles "
                             "WHERE rolname = current_user")).scalar() is False
    for statement in (f'SET ROLE "{OWNER}"', f'SET SESSION AUTHORIZATION "{OWNER}"'):
        savepoint = conn.begin_nested()
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text(statement))
        savepoint.rollback()


@pytest.mark.security
def test_even_the_owner_is_stopped_by_the_triggers(owner, owner_user):
    _, alice = owner_user
    event = record_event(owner, alice, "query", {"question": "q"})
    with pytest.raises(DBAPIError, match="append-only"):
        owner.execute(text("UPDATE audit_events SET payload = '{}' WHERE id = :i"), {"i": event})


def test_a_huge_company_id_still_gets_its_chain(conn):
    """Lock keys are 32-bit; company ids are 64-bit."""
    company = conn.execute(text("INSERT INTO companies (id, name) VALUES (3000000000, 'Big') RETURNING id")).scalar_one()
    user = conn.execute(text("INSERT INTO users (email, company_id) VALUES ('b@big.example', :c) RETURNING id"),
                        {"c": company}).scalar_one()
    record_event(conn, user, "query", {"question": "q"})
    assert verify_chain(conn, company) | {"head": None} == {
        "ok": True, "checked": 1, "first_broken_id": None, "reason": None, "head": None}


@pytest.mark.security
def test_concurrent_writes_never_fork_the_chain():
    with engine.begin() as c:
        company = c.execute(text("INSERT INTO companies (name) VALUES ('Busy') RETURNING id")).scalar_one()
        user = c.execute(text("INSERT INTO users (email, company_id) VALUES ('busy@busy.example', :c) "
                              "RETURNING id"), {"c": company}).scalar_one()
    try:
        def write():
            for _ in range(5):
                with engine.begin() as c:
                    record_event(c, user, "query", {"question": "q"})

        threads = [threading.Thread(target=write) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with engine.connect() as c:
            assert verify_chain(c, company) | {"head": None} == {
                "ok": True, "checked": 30, "first_broken_id": None, "reason": None, "head": None}
            assert len({r.prev_hash for r in chain(c, company)}) == 30  # no two records share a predecessor
    finally:
        with engine.begin() as c:  # audit records stay: the log is append-only
            c.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
            c.execute(text("DELETE FROM companies WHERE id = :c"), {"c": company})


# ---- The admin API ----

def client_for(conn, user):
    app = create_app("development")
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_tx] = lambda: within(conn)
    app.dependency_overrides[get_llm] = lambda: None
    client = TestClient(app)
    client.post("/api/dev/session", json={"user_id": user.id})
    return client


@pytest.fixture
def people(make_user, make_company):
    return {
        "admin": make_user("priya@co.example", [], is_admin=True),
        "jdoe": make_user("jdoe@co.example", []),
        "alice": make_user("alice@co.example", []),
        "outsider": make_user("olga@other.example", [], company_id=make_company("Other")),
    }


def add_doc_in(conn, company, source, source_id, scope_id):
    conn.execute(text("INSERT INTO documents (company_id, source, source_id, scope_id, updated_at) "
                      "VALUES (:c, :s, :i, :scope, now())"),
                 {"c": company, "s": source, "i": source_id, "scope": scope_id})


def ids(resp):
    return [r["id"] for r in resp.json()["records"]]


@pytest.mark.security
def test_only_admins_can_search_or_verify(conn, people):
    member = client_for(conn, people["jdoe"])
    assert member.get("/api/admin/audit").status_code == 403
    assert member.post("/api/admin/audit/verify").status_code == 403


@pytest.mark.security
def test_an_admin_sees_only_their_own_companys_records(conn, people):
    mine = query_event(conn, people["jdoe"], "jira:1")
    theirs = query_event(conn, people["outsider"], "jira:1")
    found = ids(client_for(conn, people["admin"]).get("/api/admin/audit", params={"event_type": "query"}))
    assert mine in found and theirs not in found


def test_the_challenges_audit_inquiry(conn, company, people):
    """ "Show me everything jdoe accessed related to the payment-gateway space in the last 30 days." """
    add_doc_in(conn, company, "confluence", "101", "GATEWAY")
    add_doc_in(conn, company, "confluence", "202", "HR")
    in_space = query_event(conn, people["jdoe"], "confluence:101")
    tried = query_event(conn, people["jdoe"], restricted=["confluence:101"])  # a denied attempt counts too
    query_event(conn, people["jdoe"], "confluence:202")  # another space
    query_event(conn, people["alice"], "confluence:101")  # another person
    admin_change = record_event(conn, people["admin"].id, "boundary_added",
                                {"source": "confluence", "scope_id": "GATEWAY", "title": "Payment gateway"})

    admin = client_for(conn, people["admin"])
    since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    resp = admin.get("/api/admin/audit", params={"user": "JDoe@co.example", "source": "confluence",
                                                 "scope_id": "GATEWAY", "since": since})
    assert resp.status_code == 200
    assert ids(resp) == [tried, in_space]  # newest first
    assert resp.json()["records"][0]["user_email"] == "jdoe@co.example"
    # Without the user filter, admin changes to that space are included.
    assert admin_change in ids(admin.get("/api/admin/audit", params={"source": "confluence", "scope_id": "GATEWAY"}))


def test_filters_by_document_type_and_time(conn, people):
    a = query_event(conn, people["jdoe"], "slack:C1:1")
    b = query_event(conn, people["jdoe"], denied=["slack:C1:1"])
    query_event(conn, people["jdoe"], "drive:F1")
    admin = client_for(conn, people["admin"])

    assert ids(admin.get("/api/admin/audit", params={"document": "slack:C1:1"})) == [b, a]
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert ids(admin.get("/api/admin/audit", params={"event_type": "query", "until": yesterday})) == []
    assert admin.get("/api/admin/audit", params={"event_type": "DROP TABLE"}).status_code == 422
    assert admin.get("/api/admin/audit", params={"source": "teams"}).status_code == 422
    # A scope id without its tool used to be ignored silently, returning everything.
    assert admin.get("/api/admin/audit", params={"scope_id": "GATEWAY"}).status_code == 422


def test_pages_newest_first(conn, people):
    events = [query_event(conn, people["jdoe"]) for _ in range(3)]
    admin = client_for(conn, people["admin"])
    first = admin.get("/api/admin/audit", params={"event_type": "query", "limit": 2}).json()
    assert [r["id"] for r in first["records"]] == events[:0:-1]
    second = admin.get("/api/admin/audit", params={"event_type": "query", "limit": 2,
                                                   "before_id": first["next_before_id"]}).json()
    assert [r["id"] for r in second["records"]] == events[:1] and second["next_before_id"] is None


@pytest.mark.security
def test_searching_and_verifying_are_themselves_audited(conn, company, people):
    query_event(conn, people["jdoe"])
    admin = client_for(conn, people["admin"])
    admin.get("/api/admin/audit", params={"user": "jdoe@co.example"})
    result = admin.post("/api/admin/audit/verify").json()
    assert result["ok"] and result["head"]["hash"]

    logged = conn.execute(text("SELECT event_type, payload FROM audit_events WHERE user_id = :u ORDER BY id"),
                          {"u": people["admin"].id}).all()
    assert [e for e, _ in logged] == ["audit_searched", "audit_verified"]
    assert logged[0].payload == {"filters": {"user": "jdoe@co.example", "limit": 50}, "results": 1}
    assert logged[1].payload["ok"] is True
    assert verify_chain(conn, company)["ok"]  # those records are in the chain too


@pytest.mark.security
def test_records_from_before_someone_joined_are_searchable_by_their_companys_admin_only(conn, company, people):
    newcomer = conn.execute(text("INSERT INTO users (email) VALUES ('new@co.example') RETURNING id")).scalar_one()
    before = record_event(conn, newcomer, "connector_connected", {"provider": "google"})  # no company yet
    conn.execute(text("UPDATE users SET company_id = :c WHERE id = :u"), {"c": company, "u": newcomer})

    found = ids(client_for(conn, people["admin"]).get("/api/admin/audit", params={"user": "new@co.example"}))
    assert before in found
    conn.execute(text("UPDATE users SET is_admin = true WHERE id = :u"), {"u": people["outsider"].id})
    assert before not in ids(client_for(conn, people["outsider"]).get("/api/admin/audit"))

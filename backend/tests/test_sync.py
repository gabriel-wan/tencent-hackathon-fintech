"""Sync engine and live checks, with a fake source in place of the APIs. The database is real: sync commits
its own transactions, so companies (and everything under them) are emptied around each test."""

from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app import sync
from app.connectors import live, store
from app.db import engine
from app.llm.client import EMBEDDING_MAX_CHARS
from tests.helpers import FakeLLM


def test_chunks_are_packed_and_never_too_long():
    long_line = "x" * (EMBEDDING_MAX_CHARS + 10)
    assert sync.chunk("a\n\nb") == ["a\nb"]  # blank lines dropped, short lines packed together
    assert [len(c) for c in sync.chunk(long_line)] == [EMBEDDING_MAX_CHARS, 10]
    assert all(len(c) <= EMBEDDING_MAX_CHARS for c in sync.chunk(("y" * 1500 + "\n") * 5))


def doc(source_id="C1:1", body="gateway migration blocked", acl=("slack:members",)):
    return {"source": "slack", "source_id": source_id, "scope_id": "C1", "title": "#eng", "url": "https://x",
            "updated_at": "2026-10-01T00:00:00Z", "acl": list(acl), "text": body}


def chunk_ids(conn):
    return conn.execute(text("SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id "
                             "WHERE d.source_id = 'C1:1' ORDER BY c.id")).scalars().all()


def test_upsert_rewrites_chunks_only_when_the_text_changes(conn, company):
    sync.upsert(conn, company, doc())
    first = chunk_ids(conn)
    sync.upsert(conn, company, doc(acl=["slack:user:U1"]))  # permissions changed, text did not
    assert chunk_ids(conn) == first
    assert conn.execute(text("SELECT acl FROM documents")).scalar() == ["slack:user:U1"]
    sync.upsert(conn, company, doc(body="gateway migration done"))
    assert chunk_ids(conn) != first


# ---- sync_company: a company with an admin and one Slack channel in its boundary ----

def empty():
    with engine.begin() as c:
        c.execute(text("TRUNCATE companies, users CASCADE"))


@pytest.fixture
def setup(monkeypatch):
    empty()
    with engine.begin() as c:
        company = c.execute(text("INSERT INTO companies (name) VALUES ('Acme') RETURNING id")).scalar()
        admin = c.execute(text("INSERT INTO users (email, is_admin, company_id) VALUES ('a@acme.example', true, :c) "
                               "RETURNING id"), {"c": company}).scalar()
        c.execute(text("INSERT INTO boundary (company_id, source, scope_id, scope_type) VALUES (:c, 'slack', 'C1', "
                       "'channel')"), {"c": company})
    source = SimpleNamespace(docs=[doc(), doc("C1:2", "ledger migration")], seen=[])

    def fetch(client, scope_id, changed):
        source.seen.append((client, scope_id))
        if isinstance(source.docs, Exception):
            raise source.docs
        for d in source.docs:  # like the real sources: text only when changed
            yield d if changed(d["source_id"], d["updated_at"]) else {**d, "text": None}

    source.fetch = fetch
    monkeypatch.setitem(store.SOURCES, "slack", source)
    monkeypatch.setattr(store, "client", lambda _engine, user, src: f"{src} client of user {user}")
    yield SimpleNamespace(company=company, admin=admin, source=source)
    empty()


def live_docs():
    with engine.connect() as c:
        return dict(c.execute(text("SELECT source_id, deleted_at IS NULL FROM documents")).all())


def test_sync_reads_each_scope_as_the_admin(setup):
    sync.sync_company(engine, setup.company, llm=FakeLLM())
    assert setup.source.seen == [(f"slack client of user {setup.admin}", "C1")]
    assert live_docs() == {"C1:1": True, "C1:2": True}
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM chunks WHERE embedding IS NULL")).scalar() == 0


def test_unchanged_items_keep_their_chunks_and_get_new_permissions(setup):
    sync.sync_company(engine, setup.company, llm=FakeLLM())
    with engine.connect() as c:
        before = chunk_ids(c)
    setup.source.docs = [doc(acl=["slack:user:U9"]), doc("C1:2", "ledger migration")]  # same modified time
    sync.sync_company(engine, setup.company, llm=FakeLLM())
    with engine.connect() as c:
        assert chunk_ids(c) == before
        assert c.execute(text("SELECT acl FROM documents WHERE source_id = 'C1:1'")).scalar() == ["slack:user:U9"]


def test_items_gone_from_the_source_are_soft_deleted(setup):
    sync.sync_company(engine, setup.company, llm=FakeLLM())
    setup.source.docs = [doc()]
    sync.sync_company(engine, setup.company, llm=FakeLLM())
    assert live_docs() == {"C1:1": True, "C1:2": False}


def test_a_failed_fetch_deletes_nothing(setup):
    sync.sync_company(engine, setup.company, llm=FakeLLM())
    setup.source.docs = RuntimeError("slack is down")
    sync.sync_company(engine, setup.company, llm=FakeLLM())
    assert live_docs() == {"C1:1": True, "C1:2": True}


def test_embeddings_missed_during_an_outage_are_filled_later(setup):
    sync.sync_company(engine, setup.company, llm=FakeLLM(embed_error=RuntimeError("TokenHub down")))
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM chunks WHERE embedding IS NULL")).scalar() == 2
    assert sync.embed_missing(engine, FakeLLM()) == 2
    assert sync.embed_missing(engine, FakeLLM()) == 0


# ---- Live checks: as the asking user's own connection ----

def test_live_check_asks_the_source_as_the_asking_user(setup):
    setup.source.can_read = lambda client, ids: {i for i in ids if client.endswith(str(setup.admin)) and i == "C1:1"}
    assert live.can_read(setup.admin, "slack", ["C1:1", "C1:2"]) == {"C1:1": True, "C1:2": False}
    production = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(app_env="production")))
    checkers = live.for_request(production, SimpleNamespace(id=setup.admin))([], [])
    assert checkers["slack"]("slack:user:U1", ["C1:1"]) == {"C1:1": True}  # bound to the asking user

"""HTTP contract: identity only from the session, strict request bodies, dev routes only in development."""
import json

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_conn, get_llm
from app.main import create_app


def make_client(conn, llm, app_env="development"):
    app = create_app(app_env)
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_llm] = lambda: llm
    return TestClient(app)


@pytest.fixture
def alice(make_user):
    return make_user("alice@co.example", ["slack:user:U001", "slack:members"], name="Alice")


@pytest.mark.security
def test_query_without_session_is_rejected(conn, fake_llm):
    resp = make_client(conn, fake_llm()).post("/api/query", json={"question": "hi"})
    assert resp.status_code == 401


def test_dev_sign_in_then_me(conn, fake_llm, alice):
    client = make_client(conn, fake_llm())
    assert client.post("/api/dev/session", json={"user_id": alice.id}).status_code == 200
    assert client.get("/api/me").json() == {"email": "alice@co.example", "name": "Alice", "is_admin": False}


@pytest.mark.security
def test_user_id_in_query_body_is_rejected(conn, fake_llm, alice, make_user):
    admin = make_user("priya@co.example", ["slack:user:U004"], is_admin=True)
    client = make_client(conn, fake_llm())
    client.post("/api/dev/session", json={"user_id": alice.id})
    resp = client.post("/api/query", json={"question": "hi", "user_id": admin.id})
    assert resp.status_code == 422


def test_blank_question_is_rejected(conn, fake_llm, alice):
    client = make_client(conn, fake_llm())
    client.post("/api/dev/session", json={"user_id": alice.id})
    assert client.post("/api/query", json={"question": "   "}).status_code == 422


def test_query_returns_answer_citations_and_audit_id(conn, fake_llm, alice, add_doc):
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked", title="#payments")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}))
    client = make_client(conn, llm)
    client.post("/api/dev/session", json={"user_id": alice.id})

    body = client.post("/api/query", json={"question": "gateway migration"}).json()

    assert body["answer"] == "Blocked [S1]."
    assert body["citations"][0]["id"] == "slack:C1:1"
    assert set(body["citations"][0]) == {"id", "title", "url", "source", "updated_at", "synced_at"}
    assert isinstance(body["audit_id"], int)


@pytest.mark.security
def test_dev_routes_do_not_exist_outside_development(conn, fake_llm, alice):
    client = make_client(conn, fake_llm(), app_env="production")
    assert client.post("/api/dev/session", json={"user_id": alice.id}).status_code == 404
    assert client.get("/api/dev/users").status_code == 404


def test_sign_out_ends_the_session(conn, fake_llm, alice):
    client = make_client(conn, fake_llm())
    client.post("/api/dev/session", json={"user_id": alice.id})
    assert client.delete("/api/session").status_code == 204
    assert client.get("/api/me").status_code == 401

"""End-to-end query pipeline with a fake LLM: what the model sees, what is answered, what is audited."""
import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.llm.grounding import FALLBACK_ANSWER
from app.pipeline.query import UNAVAILABLE_ANSWER, answer_question

ALICE = ["slack:user:U001", "slack:members", "google:user:alice@co.example"]


def audit_payload(conn, audit_id):
    return conn.execute(text("SELECT payload FROM audit_events WHERE id = :i"), {"i": audit_id}).scalar_one()


def deny_all_checkers(candidates, principals):
    return {"slack": lambda p, ids: {i: False for i in ids}, "drive": lambda p, ids: {i: False for i in ids}}


@pytest.mark.security
def test_content_the_user_cannot_see_never_reaches_the_llm(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked on certificate")
    add_doc("slack", "C9:1", ["slack:user:U999"], "gateway migration CANARY-SECRET-42 breach details")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}))

    answer_question(conn, alice, "gateway migration status", llm)

    assert len(llm.chat_calls) == 1
    assert "CANARY-SECRET-42" not in llm.all_prompt_text()


@pytest.mark.security
def test_nothing_allowed_means_llm_is_not_called(conn, make_user, add_doc, fake_llm):
    ben = make_user("ben@co.example", ["slack:user:U002", "slack:members"])
    add_doc("slack", "C1:1", ["slack:user:U001"], "Q3 breach report")
    llm = fake_llm()

    result = answer_question(conn, ben, "show me the Q3 breach report", llm)

    assert llm.chat_calls == []
    assert result.answer == FALLBACK_ANSWER and result.citations == []
    payload = audit_payload(conn, result.audit_id)
    assert payload["llm_called"] is False and payload["sent_to_llm"] == []


@pytest.mark.security
def test_live_check_denial_drops_a_document_the_stored_acl_allowed(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm()

    result = answer_question(conn, alice, "gateway migration", llm, checkers_factory=deny_all_checkers)

    assert llm.chat_calls == [] and result.answer == FALLBACK_ANSWER
    [candidate] = audit_payload(conn, result.audit_id)["candidates"]
    assert candidate == {"document": "slack:C1:1", "allowed": False, "reason": "denied by slack check"}


def test_answer_cites_documents_and_is_audited(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked on certificate", title="#payments")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked on the certificate [S1].", "citations": ["S1"]}))

    result = answer_question(conn, alice, "gateway migration", llm)

    assert result.answer == "Blocked on the certificate [S1]."
    [citation] = result.citations
    assert (citation.id, citation.title, citation.source) == ("slack:C1:1", "#payments", "slack")
    payload = audit_payload(conn, result.audit_id)
    assert payload["question"] == "gateway migration"
    assert payload["sent_to_llm"] == ["slack:C1:1"] and payload["citations"] == ["slack:C1:1"]
    assert payload["answer"] == result.answer and payload["model"] == "fake-model"
    assert payload["live_check_mode"].startswith("stub")


def test_invented_citation_is_removed_before_answering(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1] and hacked [S4].", "citations": ["S1", "S4"]}))

    result = answer_question(conn, alice, "gateway migration", llm)

    assert "[S4]" not in result.answer and [c.id for c in result.citations] == ["slack:C1:1"]
    assert audit_payload(conn, result.audit_id)["removed_citations"] == ["S4"]


def test_embedding_failure_falls_back_to_keyword_search(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}),
                   embed_error=RuntimeError("embedding model not enabled"))

    result = answer_question(conn, alice, "gateway migration", llm)

    assert result.citations and audit_payload(conn, result.audit_id)["search_mode"] == "keyword_only"


def test_llm_failure_returns_unavailable_message_and_is_audited(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(chat_error=RuntimeError("HTTP 500"))

    result = answer_question(conn, alice, "gateway migration", llm)

    assert result.answer == UNAVAILABLE_ANSWER and result.citations == []
    assert audit_payload(conn, result.audit_id)["llm_error"] == "RuntimeError"


@pytest.mark.security
def test_audit_events_cannot_be_updated_or_deleted(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    audit_id = answer_question(conn, alice, "anything", fake_llm()).audit_id
    for statement in ("UPDATE audit_events SET payload = '{}' WHERE id = :i",
                      "DELETE FROM audit_events WHERE id = :i"):
        savepoint = conn.begin_nested()
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text(statement), {"i": audit_id})
        savepoint.rollback()

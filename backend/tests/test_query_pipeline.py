"""End-to-end query pipeline with a fake LLM: what the model sees, what is answered, what is audited."""
import json
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.llm.client import EMBEDDING_MAX_CHARS
from app.llm.grounding import FALLBACK_ANSWER
from app.pipeline.query import MAX_CONTEXT_CHARS, UNAVAILABLE_ANSWER, answer_question
from tests.helpers import FakeLLM, within

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

    answer_question(within(conn), alice, "gateway migration status", llm)

    assert len(llm.chat_calls) == 1
    assert "CANARY-SECRET-42" not in llm.all_prompt_text()


@pytest.mark.security
def test_nothing_allowed_means_llm_is_not_called(conn, make_user, add_doc, fake_llm):
    ben = make_user("ben@co.example", ["slack:user:U002", "slack:members"])
    add_doc("slack", "C1:1", ["slack:user:U001"], "Q3 breach report")
    llm = fake_llm()

    result = answer_question(within(conn), ben, "show me the Q3 breach report", llm)

    assert llm.chat_calls == []
    assert result.answer == FALLBACK_ANSWER and result.citations == []
    payload = audit_payload(conn, result.audit_id)
    assert payload["llm_called"] is False and payload["sent_to_llm"] == []


@pytest.mark.security
def test_live_check_denial_drops_a_document_the_stored_acl_allowed(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm()

    result = answer_question(within(conn), alice, "gateway migration", llm, checkers_factory=deny_all_checkers)

    assert llm.chat_calls == [] and result.answer == FALLBACK_ANSWER
    [candidate] = audit_payload(conn, result.audit_id)["candidates"]
    assert candidate == {"document": "slack:C1:1", "allowed": False, "reason": "denied by slack check"}


def test_answer_cites_documents_and_is_audited(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked on certificate", title="#payments")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked on the certificate [S1].", "citations": ["S1"]}))

    result = answer_question(within(conn), alice, "gateway migration", llm)

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

    result = answer_question(within(conn), alice, "gateway migration", llm)

    assert "[S4]" not in result.answer and [c.id for c in result.citations] == ["slack:C1:1"]
    assert audit_payload(conn, result.audit_id)["removed_citations"] == ["S4"]


def test_embedding_failure_falls_back_to_keyword_search(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}),
                   embed_error=RuntimeError("embedding model not enabled"))

    result = answer_question(within(conn), alice, "gateway migration", llm)

    assert result.citations and audit_payload(conn, result.audit_id)["search_mode"] == "keyword_only"


def test_llm_failure_returns_unavailable_message_and_is_audited(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(chat_error=RuntimeError("HTTP 500"))

    result = answer_question(within(conn), alice, "gateway migration", llm)

    assert result.answer == UNAVAILABLE_ANSWER and result.citations == []
    assert audit_payload(conn, result.audit_id)["llm_error"] == "RuntimeError"


@pytest.mark.security
def test_audit_events_cannot_be_updated_or_deleted(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    audit_id = answer_question(within(conn), alice, "anything", fake_llm()).audit_id
    for statement in ("UPDATE audit_events SET payload = '{}' WHERE id = :i",
                      "DELETE FROM audit_events WHERE id = :i"):
        savepoint = conn.begin_nested()
        # The app's role is refused first; the triggers still stop the owner (test_audit.py).
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text(statement), {"i": audit_id})
        savepoint.rollback()


@pytest.mark.security
def test_restricted_matches_are_audited_without_changing_what_the_user_or_llm_sees(
    conn, make_user, add_doc, fake_llm
):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked on certificate")
    reply = json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]})

    before_llm = fake_llm(reply=reply)
    before = answer_question(within(conn), alice, "gateway migration", before_llm)

    add_doc("slack", "C9:1", ["slack:user:U999"], "gateway migration SECRET-BREACH-77")
    after_llm = fake_llm(reply=reply)
    after = answer_question(within(conn), alice, "gateway migration", after_llm)

    # The user and the model see exactly the same thing...
    assert after_llm.chat_calls == before_llm.chat_calls
    assert (after.answer, after.citations) == (before.answer, before.citations)
    # ...and only the audit log records the restricted match.
    assert audit_payload(conn, before.audit_id)["restricted_matches"] == []
    assert audit_payload(conn, after.audit_id)["restricted_matches"] == [
        {"document": "slack:C9:1", "reason": "user not in document ACL"}
    ]


@pytest.mark.security
def test_a_broken_checker_still_answers_and_audits(conn, make_user, add_doc, fake_llm):
    """Regression (review of PR #5): the request completes and the denial is audited."""
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm()

    def broken_checkers(candidates, principals):
        return {"slack": lambda p, ids: None, "drive": lambda p, ids: None}

    result = answer_question(within(conn), alice, "gateway migration", llm, checkers_factory=broken_checkers)

    assert result.answer == FALLBACK_ANSWER and llm.chat_calls == []
    [candidate] = audit_payload(conn, result.audit_id)["candidates"]
    assert candidate["reason"] == "slack live check gave an invalid reply"


def test_the_llm_gets_the_best_sources_within_the_context_budget(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    body = "gateway migration " + "x" * 1882  # 1,900 characters: six fit in the budget, the seventh does not
    assert 6 * len(body) <= MAX_CONTEXT_CHARS < 7 * len(body)
    for i in range(8):
        add_doc("slack", f"C1:{i}", ["slack:user:U001"], body)
    llm = fake_llm(reply=json.dumps({"answer": "Done [S1].", "citations": ["S1"]}))

    result = answer_question(within(conn), alice, "gateway migration", llm)

    assert len(audit_payload(conn, result.audit_id)["sent_to_llm"]) == 6  # the audit lists exactly what was sent
    prompt = llm.all_prompt_text()
    assert 'id="S6"' in prompt and 'id="S7"' not in prompt


def test_no_database_transaction_is_held_during_external_calls(conn, make_user, add_doc):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    open_tx, seen = [], {}

    @contextmanager
    def tx():
        open_tx.append(1)
        try:
            with within(conn)() as c:
                yield c
        finally:
            open_tx.pop()

    class LLM(FakeLLM):
        def embed(self, texts):
            seen["embed"] = bool(open_tx)
            return super().embed(texts)

        def chat(self, messages):
            seen["chat"] = bool(open_tx)
            return super().chat(messages)

    def checkers(_candidates, _principals):
        def slack(_principal, ids):
            seen["live check"] = bool(open_tx)
            return dict.fromkeys(ids, True)
        return {"slack": slack}

    llm = LLM(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}))
    answer_question(tx, alice, "gateway migration", llm, checkers_factory=checkers)
    assert seen == {"embed": False, "live check": False, "chat": False}


def test_each_step_is_timed_in_the_audit(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}))

    result = answer_question(within(conn), alice, "gateway migration", llm)

    timings = audit_payload(conn, result.audit_id)["timings_ms"]
    assert set(timings) == {"embed", "search", "live_check", "llm", "total"}
    assert timings["total"] >= max(v for k, v in timings.items() if k != "total")


# ---- Need-to-Know Shield (ADR-010) ----

CARD = "4111 1111 1111 1111"  # fictional, Luhn-valid test number
PRIYA = ["slack:user:U004", "slack:members", "google:user:priya@co.example"]
DISPUTE = f"Customer dispute: card {CARD}, NRIC S1234567D, admin password: hunter2"


def add_dispute(add_doc, need_to_know):
    add_doc("drive", "D1", ["slack:members"], DISPUTE, title="Dispute for S1234567D",
            metadata={"need_to_know": need_to_know})


@pytest.mark.security
@pytest.mark.parametrize("need_to_know", [["google:user:priya@co.example"], ["public"], ["slack:members"]])
def test_pii_is_masked_before_the_llm_for_users_without_need_to_know(conn, make_user, add_doc, fake_llm,
                                                                    need_to_know):
    alice = make_user("alice@co.example", ALICE)
    add_dispute(add_doc, need_to_know)
    llm = fake_llm(reply=json.dumps({"answer": "A dispute [S1].", "citations": ["S1"]}))

    result = answer_question(within(conn), alice, "customer dispute", llm)

    prompt = llm.all_prompt_text()
    assert CARD not in prompt and "S1234567D" not in prompt and "hunter2" not in prompt
    assert "[card ending 1111]" in prompt and "[NRIC *****567D]" in prompt
    [citation] = result.citations
    assert citation.title == "Dispute for [NRIC *****567D]"
    assert citation.redacted == {"card": 1, "nric": 2, "secret": 1}
    payload = audit_payload(conn, result.audit_id)
    assert payload["redactions"] == {"drive:D1": {"need_to_know": False, "masked": citation.redacted}}
    assert "4111" not in json.dumps(payload) and "1234567" not in json.dumps(payload)  # counts, never values


@pytest.mark.security
def test_a_handler_named_by_the_source_sees_pii_but_never_secrets(conn, make_user, add_doc, fake_llm):
    priya = make_user("priya@co.example", PRIYA)
    add_dispute(add_doc, ["google:user:priya@co.example"])
    llm = fake_llm(reply=json.dumps({"answer": f"Card {CARD} [S1].", "citations": ["S1"]}))

    result = answer_question(within(conn), priya, "customer dispute", llm)

    prompt = llm.all_prompt_text()
    assert CARD in prompt and "S1234567D" in prompt and "hunter2" not in prompt
    assert result.answer == f"Card {CARD} [S1]."  # shown to her unmasked, so the guard keeps it
    assert result.citations[0].redacted == {"secret": 1}
    assert audit_payload(conn, result.audit_id)["redactions"]["drive:D1"]["need_to_know"] is True


@pytest.mark.security
def test_answer_guard_masks_pii_the_model_was_never_given(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(reply=json.dumps({"answer": "Card 5555 5555 5555 4444 [S1].", "citations": ["S1"]}))

    result = answer_question(within(conn), alice, "gateway migration", llm)

    assert result.answer == "Card [card ending 4444] [S1]."
    assert audit_payload(conn, result.audit_id)["answer_masked"] == {"card": 1}


@pytest.mark.security
def test_secrets_in_the_question_never_reach_the_llm_or_the_audit_log(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}))

    result = answer_question(within(conn), alice, "gateway migration, token: xyz-secret-123", llm)

    assert "xyz-secret-123" not in llm.all_prompt_text()
    assert audit_payload(conn, result.audit_id)["question"] == "gateway migration, token: [secret]"


def test_colleague_emails_stay_visible(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    make_user("priya@co.example", PRIYA)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration: ask priya@co.example, not vendor@acme.example")
    llm = fake_llm(reply=json.dumps({"answer": "Ask Priya [S1].", "citations": ["S1"]}))

    answer_question(within(conn), alice, "gateway migration", llm)

    prompt = llm.all_prompt_text()
    assert "priya@co.example" in prompt and "vendor@acme.example" not in prompt


def test_a_masked_secret_cannot_push_the_question_past_the_embedding_limit(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}))
    question = "gateway migration " + "x" * 1975 + " pwd: a"  # 2,000 characters; "[secret]" is longer than "a"

    result = answer_question(within(conn), alice, question, llm)

    assert all(len(t) <= EMBEDDING_MAX_CHARS for t in llm.embed_calls[0])
    assert audit_payload(conn, result.audit_id)["search_mode"] == "hybrid"


@pytest.mark.security
def test_a_citation_link_is_masked_like_its_title(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked")
    conn.execute(text("UPDATE documents SET url = 'https://x.example/pages/1/Refund+for+S1234567D'"))
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}))

    [citation] = answer_question(within(conn), alice, "gateway migration", llm).citations

    assert "S1234567D" not in citation.url and citation.redacted == {"nric": 1}


def test_colleague_names_stay_visible_others_are_masked(conn, make_user, add_doc, fake_llm):
    alice = make_user("alice@co.example", ALICE)
    make_user("priya@co.example", PRIYA, name="Priya Nair")
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration. Customer: Priya Nair. Customer: Jane Lee")
    llm = fake_llm(reply=json.dumps({"answer": "Blocked [S1].", "citations": ["S1"]}))

    answer_question(within(conn), alice, "gateway migration", llm)

    prompt = llm.all_prompt_text()
    assert "Priya Nair" in prompt and "Jane Lee" not in prompt

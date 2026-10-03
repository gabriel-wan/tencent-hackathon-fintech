"""Permission-filtered hybrid search (ADR-005): the stored ACL and boundary filter come first."""
import pytest

from app.retrieval.search import hybrid_search
from tests.helpers import unit_vector

pytestmark = pytest.mark.security

ALICE = ["slack:user:U001", "slack:members", "public"]
BEN = ["slack:user:U002", "slack:members", "public"]


def keys(results):
    return [c.key for c in results]


def test_private_channel_member_sees_thread_and_non_member_does_not(conn, add_doc):
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked on certificate")
    assert keys(hybrid_search(conn, ALICE, "gateway migration")) == ["slack:C1:1"]
    assert hybrid_search(conn, BEN, "gateway migration") == []


def test_public_channel_is_visible_to_full_members_only(conn, add_doc):
    add_doc("slack", "C2:1", ["slack:members"], "ledger migration on Saturday")
    assert keys(hybrid_search(conn, BEN, "ledger migration")) == ["slack:C2:1"]
    guest = ["slack:user:U003", "public"]
    assert hybrid_search(conn, guest, "ledger migration") == []


def test_document_with_empty_acl_is_never_returned(conn, add_doc):
    add_doc("drive", "F1", [], "gateway migration plan")
    assert hybrid_search(conn, ALICE, "gateway migration") == []


def test_document_outside_admin_boundary_is_excluded(conn, add_doc):
    add_doc("drive", "SALARY", ["public"], "salary bands for engineers", scope_id="F_HR", in_boundary=False)
    assert hybrid_search(conn, ALICE, "salary bands") == []


def test_deleted_document_is_excluded(conn, add_doc):
    add_doc("slack", "C1:2", ["slack:members"], "gateway migration notes", deleted=True)
    assert hybrid_search(conn, ALICE, "gateway migration") == []


def test_keyword_search_matches_any_meaningful_word(conn, add_doc):
    add_doc("slack", "C1:3", ["slack:members"], "the certificate rotation lands Thursday")
    results = hybrid_search(conn, ALICE, "when does the vendor finish the certificate thing?")
    assert keys(results) == ["slack:C1:3"]


def test_semantic_search_finds_a_match_with_no_shared_words(conn, add_doc):
    add_doc("slack", "C1:4", ["slack:members"], "cert rotation stuck at vendor", embedding=unit_vector(5))
    add_doc("slack", "C1:5", ["slack:members"], "lunch menu for friday", embedding=unit_vector(9))
    results = hybrid_search(conn, ALICE, "why is the launch late", question_embedding=unit_vector(5))
    assert keys(results)[0] == "slack:C1:4"


def test_semantic_search_also_respects_the_acl(conn, add_doc):
    add_doc("slack", "C1:6", ["slack:user:U999"], "secret", embedding=unit_vector(3))
    assert hybrid_search(conn, ALICE, "anything", question_embedding=unit_vector(3)) == []

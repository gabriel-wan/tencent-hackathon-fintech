"""Permission-filtered hybrid search (ADR-005): the stored ACL and boundary filter come first."""
import pytest

from app.retrieval.search import hybrid_search
from tests.helpers import unit_vector

pytestmark = pytest.mark.security

ALICE = ["slack:user:U001", "slack:members", "public"]
BEN = ["slack:user:U002", "slack:members", "public"]


def keys(results):
    return [c.key for c in results]


def test_private_channel_member_sees_thread_and_non_member_does_not(conn, add_doc, company):
    add_doc("slack", "C1:1", ["slack:user:U001"], "gateway migration blocked on certificate")
    assert keys(hybrid_search(conn, company,ALICE, "gateway migration")) == ["slack:C1:1"]
    assert hybrid_search(conn, company,BEN, "gateway migration") == []


def test_public_channel_is_visible_to_full_members_only(conn, add_doc, company):
    add_doc("slack", "C2:1", ["slack:members"], "ledger migration on Saturday")
    assert keys(hybrid_search(conn, company,BEN, "ledger migration")) == ["slack:C2:1"]
    guest = ["slack:user:U003", "public"]
    assert hybrid_search(conn, company,guest, "ledger migration") == []


def test_another_companys_documents_are_never_returned(conn, add_doc, company, make_company):
    # `public` and `slack:members` are held in every company: only the company filter keeps them apart.
    other = make_company("Other Co")
    add_doc("slack", "C1:9", ["slack:members", "public"], "gateway migration finished", company_id=other)
    add_doc("drive", "F9", ["public"], "gateway migration budget", company_id=other)
    assert hybrid_search(conn, company, ALICE, "gateway migration") == []
    assert set(keys(hybrid_search(conn, other, ALICE, "gateway migration"))) == {"slack:C1:9", "drive:F9"}


def test_a_user_without_a_company_sees_nothing(conn, add_doc, company):
    # e.g. connected only Google Drive so far: no company yet, so not even `public` documents.
    add_doc("drive", "F8", ["public"], "gateway migration plan")
    assert hybrid_search(conn, None, ALICE, "gateway migration") == []


def test_another_companys_documents_are_not_even_audited(conn, add_doc, company, make_company):
    from app.retrieval.search import restricted_matches

    add_doc("slack", "C1:10", ["slack:user:U999"], "gateway migration secret", company_id=make_company("Other"))
    assert restricted_matches(conn, company, ALICE, "gateway migration") == []


def test_same_source_id_in_two_companies(conn, add_doc, company, make_company):
    add_doc("jira", "10001", ["public"], "gateway migration ticket")
    add_doc("jira", "10001", ["public"], "unrelated other ticket", company_id=make_company("Other"))
    assert keys(hybrid_search(conn, company, ALICE, "gateway migration")) == ["jira:10001"]


def test_document_with_empty_acl_is_never_returned(conn, add_doc, company):
    add_doc("drive", "F1", [], "gateway migration plan")
    assert hybrid_search(conn, company,ALICE, "gateway migration") == []


def test_document_outside_admin_boundary_is_excluded(conn, add_doc, company):
    add_doc("drive", "SALARY", ["public"], "salary bands for engineers", scope_id="F_HR", in_boundary=False)
    assert hybrid_search(conn, company,ALICE, "salary bands") == []


def test_deleted_document_is_excluded(conn, add_doc, company):
    add_doc("slack", "C1:2", ["slack:members"], "gateway migration notes", deleted=True)
    assert hybrid_search(conn, company,ALICE, "gateway migration") == []


def test_keyword_search_matches_any_meaningful_word(conn, add_doc, company):
    add_doc("slack", "C1:3", ["slack:members"], "the certificate rotation lands Thursday")
    results = hybrid_search(conn, company,ALICE, "when does the vendor finish the certificate thing?")
    assert keys(results) == ["slack:C1:3"]


def test_semantic_search_finds_a_match_with_no_shared_words(conn, add_doc, company):
    add_doc("slack", "C1:4", ["slack:members"], "cert rotation stuck at vendor", embedding=unit_vector(5))
    add_doc("slack", "C1:5", ["slack:members"], "lunch menu for friday", embedding=unit_vector(9))
    results = hybrid_search(conn, company,ALICE, "why is the launch late", question_embedding=unit_vector(5))
    assert keys(results)[0] == "slack:C1:4"


def test_semantic_search_also_respects_the_acl(conn, add_doc, company):
    add_doc("slack", "C1:6", ["slack:user:U999"], "secret", embedding=unit_vector(3))
    assert hybrid_search(conn, company,ALICE, "anything", question_embedding=unit_vector(3)) == []


def test_restricted_matches_lists_only_documents_the_user_cannot_see(conn, add_doc, company):
    from app.retrieval.search import restricted_matches

    add_doc("slack", "C1:7", ["slack:members"], "gateway migration status")
    add_doc("slack", "C9:7", ["slack:user:U999"], "gateway migration private notes")
    add_doc("drive", "HR:7", ["public"], "gateway migration budget", scope_id="F_HR", in_boundary=False)

    matches = {m["document"]: m["reason"] for m in restricted_matches(conn, company,ALICE, "gateway migration")}

    assert matches == {
        "slack:C9:7": "user not in document ACL",
        "drive:HR:7": "outside admin boundary",
    }


def test_restricted_matches_ignore_documents_that_are_only_semantically_near(conn, add_doc, company):
    from app.retrieval.search import restricted_matches

    # Shares no words with the question; must not be logged as "reached".
    add_doc("drive", "SALARY:8", ["slack:user:U999"], "compensation bands", embedding=unit_vector(1))
    assert restricted_matches(conn, company,ALICE, "gateway migration") == []


def test_restricted_match_is_logged_even_when_many_visible_documents_match(conn, add_doc, company):
    """Regression (review of PR #5): visible matches must not push restricted ones out."""
    from app.retrieval.search import restricted_matches

    for i in range(25):
        add_doc("slack", f"C1:{100 + i}", ["slack:members"], f"gateway migration update {i}")
    add_doc("slack", "C9:100", ["slack:user:U999"], "gateway migration private notes")

    assert restricted_matches(conn, company,ALICE, "gateway migration") == [
        {"document": "slack:C9:100", "reason": "user not in document ACL"}
    ]


def test_vector_index_search_is_not_starved_by_restricted_neighbours(conn, add_doc, company):
    """With the HNSW index in use, the 60 nearest chunks belong to documents the user
    may not see. Iterative scan must keep searching and still find the permitted one."""
    import math

    from sqlalchemy import text

    from app.llm.client import EMBEDDING_DIM
    from app.retrieval.search import RRF_K, SEARCH_SQL, vector_literal

    def at_angle(theta):
        v = [0.0] * EMBEDDING_DIM
        v[0], v[1] = math.cos(theta), math.sin(theta)
        return v

    for i in range(60):
        add_doc("slack", f"X:{i}", ["slack:user:U999"], f"restricted {i}", embedding=at_angle(0.01 * i))
    add_doc("slack", "OK:1", ["slack:user:U001"], "permitted", embedding=at_angle(0.9))
    conn.execute(text("SET LOCAL enable_seqscan = off"))  # force the index path
    conn.execute(text("SET LOCAL enable_sort = off"))

    params = {"company_id": company, "principals": ALICE, "question": "nomatch", "qvec": vector_literal(unit_vector(0)),
              "use_vec": True, "chunk_limit": 5, "rrf_k": RRF_K}
    plan = "\n".join(r[0] for r in conn.execute(text("EXPLAIN " + SEARCH_SQL.text), params))
    assert "chunks_embedding_hnsw_idx" in plan  # the query shape can use the index

    results = hybrid_search(conn, company,ALICE, "nomatch", question_embedding=unit_vector(0), chunk_limit=5)
    assert keys(results) == ["slack:OK:1"]

"""The demo seed's permission cases (app/seed.py): who can find which story documents, and the scale filler.

Searches with the stored ACLs, like the development stub does for seeded people. If a seed edit breaks one of
these, a demo step in docs/FEATURES.md breaks with it.
"""
import pytest
from sqlalchemy import text

from app import seed, seed_scale
from app.auth.principals import PUBLIC
from app.retrieval.search import hybrid_search

pytestmark = pytest.mark.security


@pytest.fixture
def seeded(conn):
    for team, name, users, boundary, documents in seed.COMPANIES:
        seed.seed_company(conn, team, name, users, boundary, documents)
    merlion = conn.execute(text("SELECT id FROM companies WHERE slack_team_id = 'T_MERLION'")).scalar_one()
    principals = {email: [*p, PUBLIC] for email, _name, _admin, p in seed.USERS}  # as principals_for() gives
    return conn, merlion, principals


def found(seeded, who: str, question: str) -> set[str]:
    conn, company, principals = seeded
    return {c.key for c in hybrid_search(conn, company, principals[who], question)}


def test_project_status_leaves_out_the_private_channel_alice_is_not_in(seeded):
    alice = found(seeded, "alice@merlionpay.example", "ledger database migration blocker")
    assert {"jira:10101", "slack:C_ENG:1728291600.000600"} <= alice
    assert "slack:C_DBTEAM:1728295200.000100" not in alice  # #db-team: Ben and Priya only
    assert "slack:C_DBTEAM:1728295200.000100" in found(seeded, "ben@merlionpay.example", "ledger migration slip")


def test_root_cause_and_follow_up_tickets_are_found(seeded):
    alice = found(seeded, "alice@merlionpay.example", "root cause payment outage follow-up tickets")
    assert {"confluence:20101", "jira:10201", "jira:10202"} <= alice


def test_one_answer_can_draw_on_all_four_tools_but_not_the_restricted_contract(seeded):
    alice = found(seeded, "alice@merlionpay.example", "PAY-412 gateway vendor decision comparison contract")
    assert {"jira:10301", "confluence:20301", "drive:D_VENDOR_CMP"} <= alice
    assert "confluence:20302" not in alice  # the contract terms: Priya only
    assert "confluence:20302" in found(seeded, "priya@merlionpay.example", "gateway contract terms")


def test_the_contractor_never_reaches_the_breach_report(seeded):
    charlie = found(seeded, "charlie@contractor.example", "Q3 breach report")
    assert "confluence:20401" not in charlie and "drive:D_Q3_INCIDENT" not in charlie
    assert "confluence:20402" in found(seeded, "charlie@contractor.example", "contractor access policy")


def test_another_companys_migration_ticket_is_never_found(seeded):
    assert "jira:90101" not in found(seeded, "alice@merlionpay.example", "database migration done")


def test_the_scale_filler_matches_company_a_and_is_the_same_every_run():
    boundary, documents = seed_scale.generate()
    by_tool = {t: sum(d[0] == t for d in documents) for t in ("confluence", "jira", "slack", "drive")}
    assert by_tool == {"confluence": 12_000, "jira": 3_000, "slack": 4_000, "drive": 1_980}
    assert len({(d[0], d[1]) for d in documents}) == len(documents)  # unique per tool
    assert all(scope_id.startswith(seed_scale.SCOPE_PREFIX) for _s, scope_id, _t, _ti in boundary)
    assert seed_scale.generate() == (boundary, documents)


def test_scale_filler_is_added_once_and_removed_cleanly(seeded, monkeypatch):
    conn, company, _principals = seeded
    small_scale(monkeypatch)
    count = lambda: conn.execute(text("SELECT count(*) FROM documents WHERE metadata->>'seed' = 'scale'")).scalar()  # noqa: E731
    added = seed.seed_scale(conn, "T_MERLION")
    assert added == count() > 0
    assert seed.seed_scale(conn, "T_MERLION") == 0  # a re-run adds nothing
    story = conn.execute(text("SELECT count(*) FROM documents WHERE company_id = :c"), {"c": company}).scalar()
    assert seed.remove_scale(conn) == added
    assert count() == 0
    assert conn.execute(text("SELECT count(*) FROM documents WHERE company_id = :c"), {"c": company}).scalar() \
        == story - added  # the story documents stay
    assert conn.execute(text("SELECT count(*) FROM boundary WHERE scope_id LIKE 'SC\\_%'")).scalar() == 0


def test_removing_the_filler_never_touches_a_real_scope_that_looks_alike(seeded):
    conn, company, _principals = seeded
    conn.execute(text("INSERT INTO boundary (company_id, source, scope_id, scope_type) "
                      "VALUES (:c, 'jira', 'SCRUM', 'project')"), {"c": company})
    seed.remove_scale(conn)
    assert conn.execute(text("SELECT count(*) FROM boundary WHERE scope_id = 'SCRUM'")).scalar() == 1


def small_scale(monkeypatch):
    for name, value in (("CONFLUENCE_SPACES", 2), ("PAGES_PER_SPACE", 3), ("JIRA_PROJECTS", 1),
                        ("SLACK_CHANNELS", 2), ("DRIVE_TOP", 1)):
        monkeypatch.setattr(seed_scale, name, value)


def test_filler_is_keyword_only_except_a_fixed_sample(seeded, monkeypatch):
    conn, _company, _principals = seeded
    small_scale(monkeypatch)
    seed.seed_scale(conn, "T_MERLION")
    to_embed = lambda: conn.execute(text(  # noqa: E731
        "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.metadata->>'seed' = 'scale' AND NOT c.keyword_only ORDER BY c.id")).scalars().all()
    assert to_embed() == []  # the sync worker leaves all of it alone
    assert seed.choose_filler_sample(conn, 3) == 3
    sample = to_embed()
    assert seed.choose_filler_sample(conn, 3) == 0 and to_embed() == sample  # the same ones, not more
    conn.execute(text("UPDATE chunks SET keyword_only = false"))  # e.g. filler from before migration 0008
    seed.seed_scale(conn, "T_MERLION")
    assert to_embed() == []  # a re-run marks it keyword-only again


def test_handlers_are_keyed_by_tool_and_id(seeded):
    conn, _company, _principals = seeded
    need = conn.execute(text("SELECT metadata->'need_to_know' FROM documents WHERE source = 'jira' "
                             "AND source_id = '10601'")).scalar()
    assert need == ["atlassian:user:A001"]


@pytest.mark.parametrize("argv", [["--embed-sample"], ["--embed-sample", "x"], ["--embed-sample", "-1"],
                                  ["--embed-smaple", "5"]])
def test_bad_flags_stop_with_a_usage_error(argv):
    with pytest.raises(SystemExit):
        seed.parse_args(argv)


def test_flags_in_either_spelling():
    assert seed.parse_args(["--embed", "--embed-sample=200"]).embed_sample == 200
    assert seed.parse_args(["--scale"]).embed_sample == 2000

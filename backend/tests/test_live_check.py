"""Live check (ADR-003): deny by default on anything other than an explicit True."""
import time
from dataclasses import dataclass, field

import pytest

from app.auth.live_check import default_checkers, live_check

pytestmark = pytest.mark.security

PRINCIPALS = ["slack:user:U1", "slack:members", "google:user:a@x.example", "public"]


@dataclass
class Cand:
    document_id: int
    source: str
    source_id: str
    acl: list[str] = field(default_factory=list)


def test_confirmed_document_is_allowed():
    [d] = live_check([Cand(1, "slack", "a")], PRINCIPALS, {"slack": lambda p, ids: {"a": True}})
    assert d.allowed


def test_false_missing_or_non_boolean_answers_deny():
    cands = [Cand(1, "slack", "a"), Cand(2, "slack", "b"), Cand(3, "slack", "c")]
    decisions = live_check(cands, PRINCIPALS, {"slack": lambda p, ids: {"a": False, "c": "yes"}})
    assert [d.allowed for d in decisions] == [False, False, False]


def test_checker_receives_the_users_own_platform_identity():
    seen = {}

    def can_read(principal, ids):
        seen["principal"] = principal
        return {i: True for i in ids}

    live_check([Cand(1, "drive", "f")], PRINCIPALS, {"drive": can_read})
    assert seen["principal"] == "google:user:a@x.example"


def test_checker_error_denies():
    def boom(principal, ids):
        raise RuntimeError("slack is down")

    [d] = live_check([Cand(1, "slack", "a")], PRINCIPALS, {"slack": boom})
    assert not d.allowed and "failed" in d.reason


def test_timeout_denies_without_waiting_for_the_checker():
    def slow(principal, ids):
        time.sleep(1.0)
        return {i: True for i in ids}

    start = time.monotonic()
    [d] = live_check([Cand(1, "slack", "a")], PRINCIPALS, {"slack": slow}, timeout_s=0.1)
    assert not d.allowed and "timed out" in d.reason
    assert time.monotonic() - start < 0.8


def test_no_linked_account_denies_without_calling_the_checker():
    called = []
    [d] = live_check(
        [Cand(1, "slack", "a")], ["google:user:a@x.example", "public"],
        {"slack": lambda p, ids: called.append(1) or {"a": True}},
    )
    assert not d.allowed and called == []


def test_source_without_a_checker_is_denied():
    [d] = live_check([Cand(1, "jira", "PAY-1")], PRINCIPALS + ["atlassian:user:x"], {})
    assert not d.allowed


def test_one_failing_source_does_not_affect_another():
    cands = [Cand(1, "slack", "a"), Cand(2, "drive", "f")]
    decisions = live_check(cands, PRINCIPALS, {
        "slack": lambda p, ids: (_ for _ in ()).throw(RuntimeError("down")),
        "drive": lambda p, ids: {"f": True},
    })
    assert [d.allowed for d in decisions] == [False, True]


def test_stub_answers_from_stored_acl():
    cands = [Cand(1, "slack", "a", ["slack:user:U1"]), Cand(2, "slack", "b", ["slack:user:U9"])]
    decisions = live_check(cands, PRINCIPALS, default_checkers(cands, PRINCIPALS))
    assert [d.allowed for d in decisions] == [True, False]


@pytest.mark.parametrize("reply", [None, {"a"}, ["a"], "a"])
def test_a_reply_that_is_not_a_mapping_denies_instead_of_crashing(reply):
    """Regression (review of PR #5): a bad reply must deny, not fail the request."""
    [d] = live_check([Cand(1, "slack", "a")], PRINCIPALS, {"slack": lambda p, ids: reply})
    assert not d.allowed and d.reason == "slack live check gave an invalid reply"


def test_a_bad_reply_from_one_source_does_not_affect_another():
    cands = [Cand(1, "slack", "a"), Cand(2, "drive", "f")]
    decisions = live_check(cands, PRINCIPALS, {
        "slack": lambda p, ids: None,
        "drive": lambda p, ids: {"f": True},
    })
    assert [d.allowed for d in decisions] == [False, True]

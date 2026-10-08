"""Need-to-Know Shield (ADR-010): what is masked, for whom, and that masking is deterministic and safe.

All values are fictional test formats (e.g. the 4111... test card).
"""
import time

import pytest

from app.llm.client import EMBEDDING_MAX_CHARS
from app.redaction import Shield, for_embedding, has_need_to_know, mask_secrets

CARD = "4111 1111 1111 1111"  # Luhn-valid test card number


def masked(text: str, **kwargs) -> str:
    return Shield(**kwargs).redact(text, cleared=False)[0]


POSITIVES = [
    (f"Card {CARD} was charged twice", "Card [card ending 1111] was charged twice"),
    ("Paid with 4242-4242-4242-4242.", "Paid with [card ending 4242]."),
    ("visa no. 4111 1111 1111 1112", "visa no. [card ending 1112]"),  # fails Luhn, but a card word precedes it
    ("Customer NRIC S1234567D called", "Customer NRIC [NRIC *****567D] called"),
    ("fin g7654321k", "fin [NRIC *****321K]"),
    ("IBAN GB82 WEST 1234 5698 7654 32 USD", "IBAN [IBAN ending 5432] USD"),
    ("Refund to account no. 123-45678-9", "Refund to account no. [account ending 6789]"),
    ("passport number E1234567", "passport number [passport 1]"),
    ("DOB: 12/03/1990", "DOB: [date of birth]"),
    ("call +65 9123 4567 today", "call [phone 1] today"),
    ("call 9123 4567.", "call [phone 1]."),
    ("mail jane.doe@gmail.com", "mail [email 1]"),
    ("Card ４１１１ １１１１ １１１１ １１１１", "Card [card ending １１１１]"),  # full-width digits
    ("my dob is 1990-03-12", "my dob is [date of birth]"),  # the way people write it
    ("her account number is 123-45678-9", "her account number is [account ending 6789]"),
    ("passport no. was E1234567", "passport no. was [passport 1]"),
]


@pytest.mark.security
@pytest.mark.parametrize("raw, expected", POSITIVES)
def test_sensitive_identifiers_are_masked(raw, expected):
    assert masked(raw) == expected


@pytest.mark.parametrize("raw", [
    "Order 4111 1111 1111 1112 shipped",  # 16 digits failing Luhn, no card word nearby
    "The ledger migration runs 2026-10-02 at 02:00.",
    "PAY-412 is blocked; see thread 1727741000.000100",
    "Step 4: if the error rate exceeds 2% for 5 minutes, fail over.",
    "Use the card ending 4242 on the account ending 6789.",
    "312 merchant accounts were reset in Q3 2026.",
    "Thread: https://x.slack.com/archives/C1/p4111111111111111",  # Luhn-valid digits inside a link or ID
    "The secrets: none here. Tokens are rotated monthly.",
    "if password == '' or token != expected: raise",  # comparisons in code are not assignments
])
def test_ordinary_text_is_left_alone(raw):
    assert masked(raw) == raw


SECRETS = [
    ("key AKIAIOSFODNN7EXAMPLE here", "key [secret] here"),
    ("token xoxb-1234567890-abcdefghij", "token [secret]"),
    ("password: hunter2", "password: [secret]"),
    ("API_KEY=sk-abcdefghijklmnopqrstuvwx", "API_KEY=[secret]"),
    ("Authorization: Bearer abcdefghijklmnop1234", "Authorization: Bearer [secret]"),
    ("jwt eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl", "jwt [secret]"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----", "[secret]"),
    # Pasted config and env files: the commonest way credentials end up in Slack and wikis.
    ("DB_PASSWORD=hunter2", "DB_PASSWORD=[secret]"),
    ("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENG", "AWS_SECRET_ACCESS_KEY=[secret]"),
    ("TOKEN_ENCRYPTION_KEY=abc123def456", "TOKEN_ENCRYPTION_KEY=[secret]"),
    ('{"password": "hunter 2", "user": "app"}', '{"password": [secret], "user": "app"}'),
    ("DATABASE_URL=postgresql://app:s3cretpw@db:5432/brain", "DATABASE_URL=postgresql://app:[secret]@db:5432/brain"),
]


def test_each_secret_is_counted_once():
    assert Shield().redact("token: xoxb-1234567890-abcdefghij", cleared=False) == ("token: [secret]", {"secret": 1})


@pytest.mark.security
@pytest.mark.parametrize("cleared", [False, True])
@pytest.mark.parametrize("raw, expected", SECRETS)
def test_secrets_are_masked_for_everyone(raw, expected, cleared):
    assert Shield().redact(raw, cleared=cleared)[0] == expected


@pytest.mark.security
def test_need_to_know_sees_pii_but_never_secrets():
    text, counts = Shield().redact(f"Card {CARD}, NRIC S1234567D, password: hunter2", cleared=True)
    assert text == f"Card {CARD}, NRIC S1234567D, password: [secret]"
    assert counts == {"secret": 1}


@pytest.mark.security
@pytest.mark.parametrize("need_to_know, expected", [
    (["google:user:priya@co.example"], True),
    (["atlassian:user:5b10-sara"], False),       # someone else's identity
    (["public"], False),                         # never an identity, even if a connector writes it
    (["slack:members"], False),
    (["google:domain:co.example"], False),
    ("google:user:priya@co.example", False),     # malformed metadata: not a list
    ([], False),
])
def test_only_the_users_own_identity_grants_need_to_know(need_to_know, expected):
    principals = ["public", "slack:members", "google:domain:co.example", "google:user:priya@co.example"]
    assert has_need_to_know(principals, need_to_know) is expected


def test_colleague_emails_stay_visible_others_are_masked():
    shield = Shield(colleagues=["Priya@co.example"])
    assert shield.redact("ask priya@co.example about jane@gmail.com", cleared=False)[0] == \
        "ask priya@co.example about [email 1]"


def test_same_value_gets_the_same_tag_across_documents():
    shield = Shield()
    first = shield.redact("from a@x.example and b@x.example", cleared=False)[0]
    second = shield.redact("again A@x.example", cleared=False)[0]
    assert (first, second) == ("from [email 1] and [email 2]", "again [email 1]")


def test_masking_twice_changes_nothing():
    once = masked("\n".join(raw for raw, _ in POSITIVES + SECRETS))
    assert masked(once) == once


@pytest.mark.security
def test_answer_guard_masks_values_the_user_was_not_shown():
    shield = Shield()
    shield.redact(f"Card {CARD}", cleared=True)  # shown unmasked from a need-to-know document
    answer = f"Card {CARD} and card 5555 5555 5555 4444, phone 9123 4567 [S1]."

    text, counts = shield.guard(answer, question="is 9123 4567 the customer's phone?")

    assert text == f"Card {CARD} and card [card ending 4444], phone 9123 4567 [S1]."
    assert counts == {"card": 1}


@pytest.mark.security
def test_secrets_are_removed_from_the_question():
    assert mask_secrets(f"password: hunter2 for card {CARD}") == f"password: [secret] for card {CARD}"


@pytest.mark.security
def test_embedding_text_is_masked_and_fits_the_model_limit():
    raw = "a@b.co " * 285  # under the limit raw; "[email 1] " is longer, so masking overflows it
    assert len(raw) <= EMBEDDING_MAX_CHARS
    out = for_embedding(raw)
    assert "@" not in out and len(out) <= EMBEDDING_MAX_CHARS


@pytest.mark.parametrize("attack", ["a" * 200_000, "1" * 200_000, "a." * 100_000, "1 " * 100_000,
                                    "+1" * 100_000, "account " * 25_000, "a://b" * 40_000, 'password:"' * 20_000,
                                    "DB_PASSWORD" * 20_000])
def test_hostile_input_cannot_stall_the_shield(attack):
    start = time.perf_counter()
    Shield().redact(attack, cleared=False)
    assert time.perf_counter() - start < 1.0

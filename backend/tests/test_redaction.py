"""Need-to-Know Shield (ADR-010): what is masked, for whom, and that masking is deterministic and safe.

All values are fictional test formats (e.g. the 4111... test card).
"""
import time

import pytest

from app.llm.client import EMBEDDING_MAX_CHARS
from app.redaction import (
    Shield,
    for_embedding,
    has_need_to_know,
    mask_secrets,
    names_in,
    protected_spans,
)

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
    ("Card ４１１１ １１１１ １１１１ １１１１", "Card [card ending 1111]"),  # full-width digits
    # Hidden and full-width characters the model reads past (normalised before detection).
    ("card 4111\u200b1111\u200b1111\u200b1111", "card [card ending 1111]"),
    ("NRIC Ｓ１２３４５６７Ｄ", "NRIC [NRIC *****567D]"),
    ("card 4111\u00a01111\u00a01111\u00a01111", "card [card ending 1111]"),  # no-break spaces
    ("card 4111\ufe0f1111\ufe0f1111\U000e01001111", "card [card ending 1111]"),  # variation selectors
    ("mail jane＠gmail．com", "mail [email 1]"),
    ("card 4111\u20131111\u20131111\u20131111", "card [card ending 1111]"),  # en dashes
    ("DOB: 12\u201303\u20131990", "DOB: [date of birth]"),  # any detector reads any dash as a hyphen
    # Only masked values change: Chinese punctuation and full-width spaces around them stay as written.
    ("\u59d3\u540d\uff1a\u5f20\u4f1f\uff0c\u7535\u8bdd\uff08\u624b\u673a\uff09\uff01\u3000\u597d\u7684", "\u59d3\u540d\uff1a[name 1]\uff0c\u7535\u8bdd\uff08\u624b\u673a\uff09\uff01\u3000\u597d\u7684"),
    ("my dob is 1990-03-12", "my dob is [date of birth]"),  # the way people write it
    ("her account number is 123-45678-9", "her account number is [account ending 6789]"),
    ("passport no. was E1234567", "passport no. was [passport 1]"),
    # Written straight after Chinese text: no ASCII word boundary, and the Chinese words around stay.
    ("信用卡4111 1111 1111 1111已退款", "信用卡[card ending 1111]已退款"),
    ("身份证S1234567D", "身份证[NRIC *****567D]"),
    ("电话91234567", "电话[phone 1]"),
    ("电话+65 9123 4567", "电话[phone 1]"),
    ("邮箱jane.lee@gmail.com的", "邮箱[email 1]的"),
    ("护照passport no. E1234567", "护照passport no. [passport 1]"),
    # Chinese labels and full-width colons.
    ("账号：123-45678-9", "账号：[account ending 6789]"),
    ("护照号码：E1234567", "护照号码：[passport 1]"),
    ("出生日期：1990年3月12日", "出生日期：[date of birth]"),
    ("卡号4111 1111 1111 1112", "卡号[card ending 1112]"),  # fails Luhn, but 卡 (card) precedes it
    # Formats the first pass missed.
    ("tel: 012-345 6789", "tel: [phone 1]"),  # a phone with no + and not Singaporean, after a label
    ("Card 4111.1111.1111.1111", "Card [card ending 1111]"),
    ("write to josé@exämple.com", "write to [email 1]"),
    # Names after a label or an honorific, and Singapore addresses.
    ("Customer: Jane Lee (jane@x.example)", "Customer: [name 1] ([email 1])"),
    ("Mdm Tan Ah Kow called twice", "Mdm [name 1] called twice"),
    ("姓名：张伟", "姓名：[name 1]"),
    ("Blk 123 Ang Mo Kio Ave 3 #12-345 Singapore 560123", "Blk [address] Ang Mo Kio Ave 3 #[address] Singapore [address]"),
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
    "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit",  # an ID in a link path
    "https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",  # an ID in a query string
    "git sha 4b825dc642cb6eb9a060e54bf8d69288fbee4904",  # lower-case hex is not a random secret
    "Deploy block 3 of the migration; PR #123 merged.",
    "The customer called twice about the refund.",
])
def test_ordinary_text_is_left_alone(raw):
    assert masked(raw) == raw


SECRETS = [
    ("key AKIAIOSFODNN7EXAMPLE here", "key [secret] here"),
    ("密钥AKIAIOSFODNN7EXAMPLE", "密钥[secret]"),
    ("token xoxb-1234567890-abcdefghij", "token [secret]"),
    ("password: hunter2", "password: [secret]"),
    ("password: hunter2, then log in.", "password: [secret], then log in."),  # the comma is not the password
    ("STRIPE_LIVE=AbCdEfGhIjKlMnOpQrStUvWxYz0123456789==", "STRIPE_LIVE=[secret]"),  # the name stays
    ("https://x.blob.example/f.pdf?sv=2024&sig=AbC%2Fdef123&se=2026", "https://x.blob.example/f.pdf?sv=2024&sig=[secret]&se=2026"),
    ("密码：abc123，然后登录", "密码：[secret]，然后登录"),
    ('"password": "hunter2,"', '"password": [secret]'),  # quoted: all of it, punctuation included
    ("DB_PASS\u200dWORD=hunter2hunter2", "DB_PASS\u200dWORD=[secret]"),  # zero-width joiner inside the name
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
    ("password：hunter2", "password：[secret]"),  # full-width colon
    ("密码：abc123然后登录", "密码：[secret]然后登录"),  # Chinese label; the sentence after it stays
    ("use wJalrXUtnFEMI7K7MDENGbPxRfiCYEXAMPLEKEY12 for prod", "use [secret] for prod"),  # random, no label
    # A private key's body without its BEGIN line (cut into another chunk): each base64 line still masked.
    ("MIIEowIBAAKCAQEA3Tz2mr7SZiAMfQyuvBjM2Bx/9a+PbNcdeL2Xr8iBm6q1qYz0\nQwJkLm7nE8fGhT3vK9pXyZ2aBcDeFgHiJkLmNoPq",
     "[secret]\n[secret]"),
]


def test_colleague_names_stay_visible():
    shield = Shield(colleague_names=["Priya Nair (admin and compliance)"])
    assert shield.redact("Customer: Priya Nair. Customer: Jane Lee", cleared=False)[0] == \
        "Customer: Priya Nair. Customer: [name 1]"


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
def test_the_audit_masks_what_the_handler_was_shown_even_without_a_label():
    shield = Shield()
    shield.redact("Customer: Jane Lee, Blk 1", cleared=True)  # a handler sees both

    assert shield.mask_all("customer Jane Lee, Mr Tan, Blk 1") == "customer [name 2], Mr [name 1], Blk [address]"


def shield_knowing(*texts: str, **kwargs) -> Shield:
    shield = Shield(**kwargs)
    shield.know(names_in(texts))
    return shield


@pytest.mark.security
def test_a_name_found_anywhere_is_masked_everywhere_with_one_tag():
    shield = shield_knowing("Customer: Jane Lee disputes a charge", "Jane called back; Lee is upset")

    text, counts = shield.redact("Jane called back; Lee is upset. Jane Lee again.", cleared=False)

    assert text == "[name 1] called back; [name 1] is upset. [name 1] again."
    assert counts == {"name": 3}


@pytest.mark.parametrize("labelled, elsewhere", [
    ("Project Name: Gateway Migration", "The Payment Gateway Migration (PAY-412) is blocked"),
    ("Client: DBS Bank", "DBS transfer to DBS Bank pending"),
    ("Payee: Singapore Power", "The Singapore office pays Singapore Power monthly"),
    ("Name: Payments Runbook", "Payments on-call runbook"),
    ("户名：新加坡电力", "新加坡电力的账单"),
    ("from jane.lee@example.com", "Jane Lee called"),  # an address is no label: it may be a team's
])
def test_a_generic_label_masks_its_value_in_place_only(labelled, elsewhere):
    # Organisations and projects carry these labels too: propagating them would mask ordinary words.
    shield = shield_knowing(labelled, elsewhere)

    assert shield.redact(elsewhere, cleared=False)[0] == elsewhere
    assert shield.redact(labelled, cleared=False)[0] != labelled  # still masked where it is labelled


def test_colleague_names_and_their_parts_stay_visible():
    shield = shield_knowing("Customer: Alice Wong", "Mr Ben Lim", colleague_names=["Alice Tan (payments engineer)",
                                                                                    "Ben Lim"])

    assert shield.redact("Alice Wong asked Alice and Ben Lim", cleared=False)[0] == "[name 1] asked Alice and Ben Lim"


@pytest.mark.security
def test_the_guard_keeps_a_first_name_only_for_a_reader_shown_the_full_name():
    source = "Customer: Jane Lee"
    handler, other = shield_knowing(source), shield_knowing(source)
    handler.redact(source, cleared=True)
    other.redact(source, cleared=False)

    assert handler.guard("Jane is waiting", question="any update?")[0] == "Jane is waiting"
    assert other.guard("Jane is waiting", question="any update?")[0] == "[name 1] is waiting"
    assert other.guard("Jane is waiting", question="is Jane waiting?")[0] == "Jane is waiting"  # typed by the user


@pytest.mark.security
def test_chunks_are_not_cut_inside_an_identifier_split_by_hidden_characters():
    raw = "pay card 4111\u200b1111\u200b1111\u200b1111 now"
    start, end = raw.index("4111"), raw.index(" now")

    assert any(s <= start and e >= end for s, e in protected_spans(raw))


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

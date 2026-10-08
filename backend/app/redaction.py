"""Need-to-Know Shield (ADR-010): deterministic masking of sensitive identifiers wherever document
text leaves our system: the LLM prompt, citation titles, the answer, and embeddings.

Authorization decides WHICH documents a user may read (ADR-003); the Shield decides which identifiers
inside them they see. A document's handlers, as its source names them (`metadata.need_to_know`: Jira
assignee and reporter, Drive owners and editors, Confluence owner and author), see it unmasked.
Everyone else sees typed tags. Secrets are masked for everyone, always. Recall over precision: when
in doubt, mask. Stored chunks stay raw; masking happens on the way out.
"""
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable

from app.auth.principals import IDENTITY_PREFIX
from app.llm.client import EMBEDDING_MAX_CHARS

_IDENTITIES = tuple(set(IDENTITY_PREFIX.values()))
_CARD_WORD = re.compile(r"(?i)\b(?:card|visa|master ?card|amex|pan|cc|credit|debit)\b")


def _decimals(value: str) -> list[int]:
    return [int(c) for c in value if c.isdecimal()]  # \d is any Unicode decimal; int() reads them all


def _luhn(digits: list[int]) -> bool:
    return sum(d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2)
               for i, d in enumerate(reversed(digits))) % 10 == 0


# Each check returns how many characters of group "v" are sensitive (0: none, leave as is).
def _whole(m: re.Match) -> int:
    return len(m["v"])


def _card(m: re.Match) -> int:  # Luhn-valid, or a card word just before it (a mistyped number)
    near = _CARD_WORD.search(m.string, max(0, m.start() - 30), m.start())
    return len(m["v"]) if _luhn(_decimals(m["v"])) or near else 0


def _iban(m: re.Match) -> int:
    """Longest prefix, ending at a group, that passes mod-97. Prefixes ending in a digit go first: the
    pattern can swallow a following word ("... 32 USD"), and 1 in 97 of those also passes."""
    v = m["v"]
    ends = [len(v)] + [i for i in range(len(v) - 1, 0, -1) if v[i] == " "]
    for end in sorted(ends, key=lambda e: (not v[e - 1].isdigit(), -e)):
        compact = v[:end].replace(" ", "")
        if 15 <= len(compact) <= 34 and int("".join(str(int(c, 36)) for c in compact[4:] + compact[:4])) % 97 == 1:
            return end
    return 0


def _at_least(n: int, most: int = 99) -> Callable[[re.Match], int]:
    return lambda m: len(m["v"]) if n <= len(_decimals(m["v"])) <= most else 0


_NUMBER_WORD = r"(?:\s*(?:no\.?|number|num|#))?(?:\s+(?:is|was))?\s*[:#]?\s*"  # "account number is 123..."

# (kind, pattern with the sensitive value in group "v", check), applied in this order. Tags left by an
# earlier detector hold at most 4 digits, so later ones never match them. Patterns that scan runs of
# characters start with a look-behind, so a long run without a match costs linear time, not quadratic.
DETECTORS: list[tuple[str, re.Pattern, Callable[[re.Match], int]]] = [
    ("secret", re.compile(r"(?P<v>-----BEGIN[A-Z ]*PRIVATE KEY-----.*?(?:-----END[A-Z ]*PRIVATE KEY-----|\Z))",
                          re.S), _whole),
    ("secret", re.compile(r"\b(?P<v>(?:AKIA|ASIA)[A-Z0-9]{16})\b"), _whole),
    ("secret", re.compile(r"\b(?P<v>xox[abposr]-[A-Za-z0-9-]{10,})"), _whole),
    ("secret", re.compile(r"\b(?P<v>gh[pousr]_[A-Za-z0-9]{30,})"), _whole),
    ("secret", re.compile(r"\b(?P<v>AIza[0-9A-Za-z_-]{35})"), _whole),
    ("secret", re.compile(r"\b(?P<v>sk-[A-Za-z0-9_-]{20,})"), _whole),
    ("secret", re.compile(r"\b(?P<v>eyJ[\w-]{5,}\.eyJ[\w-]{5,}\.[\w-]+)"), _whole),
    ("secret", re.compile(r"(?i)\bbearer\s+(?P<v>[\w.~+/-]{16,}=*)"), _whole),
    # A credential word, alone or ending a name (DB_PASSWORD=, "api_key":), then its value. A value that is
    # already a tag is skipped, so a token masked above is not counted twice.
    ("secret", re.compile(r"(?i)(?<![a-z0-9])(?:password|passwd|pwd|passcode|secret|token|"
                          r"(?:api|access|private|encryption|signing)[ _-]?key)(?![a-z0-9])[\"']?\s*"
                          r"(?:=(?!=)|:)\s*"  # an assignment, not a comparison (==)
                          r"(?P<v>(?!\[secret\])(?:\"[^\"\n]*\"|'[^'\n]*'|\S+))"), _whole),
    # user:pass@ in a URL. The scheme is bounded: unbounded, every word start rescans the rest (quadratic).
    ("secret", re.compile(r"(?i)\b[a-z][a-z0-9+.-]{0,30}://[^\s/:@]+:(?P<v>[^\s/@]+)@"), _whole),
    ("iban", re.compile(r"\b(?P<v>[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30})\b"), _iban),
    # Not glued to a letter: digits inside IDs and links (Slack's /p1727...) are not cards.
    ("card", re.compile(r"(?<!\w)(?P<v>\d(?:[ -]?\d){12,18})(?!\d)"), _card),
    ("account", re.compile(rf"(?i)\b(?:account|acct|a/c){_NUMBER_WORD}(?P<v>\d[\d -]{{4,24}}\d)"), _at_least(6)),
    ("nric", re.compile(r"(?i)\b(?P<v>[STFGM]\d{7}[A-Z])\b"), _whole),
    ("passport", re.compile(rf"(?i)\bpassport{_NUMBER_WORD}(?P<v>[A-Z]{{1,2}}\d{{6,8}}[A-Z]?)\b"), _whole),
    ("dob", re.compile(r"(?i)\b(?:dob|d\.o\.b\.?|date\s+of\s+birth|born(?:\s+on)?)(?:\s+(?:is|was))?\s*[:-]?\s*"
                       r"(?P<v>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}"
                       r"|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})"), _whole),
    ("email", re.compile(r"(?<![\w.+-])(?P<v>[\w.+-]{1,64}@[\w-]+(?:\.[\w-]+)+)"), _whole),
    ("phone", re.compile(r"(?<![\w+])(?P<v>\+\d{1,3}(?:[ .-]?\(?\d{1,4}\)?){2,5})"), _at_least(8, 15)),
    ("phone", re.compile(r"(?<![\w.+/-])(?P<v>(?:\(?65\)?[ -]?)?[3689]\d{3}[ -]?\d{4})(?![\w]|[.-]\d)"), _whole),
]


def _key(kind: str, value: str) -> str:
    """Comparable form of a value: emails by address, numbers without separators."""
    return value.lower() if kind == "email" else re.sub(r"[\W_]", "", value.lower())


class Shield:
    """One per question, so the same value gets the same tag in every source, and the answer guard
    knows which values were shown unmasked."""

    def __init__(self, colleagues: Iterable[str] = ()):
        self.colleagues = {e.lower() for e in colleagues}  # the asker's company's users: not masked
        self._numbers: dict[str, dict[str, int]] = defaultdict(dict)
        self._shown: set[str] = set()

    def redact(self, text: str, cleared: bool) -> tuple[str, Counter]:
        """Mask `text` for this reader. `cleared` (need-to-know): only secrets are masked."""
        def keep(kind: str, key: str) -> bool:
            if kind != "secret" and (cleared or kind == "email" and key in self.colleagues):
                self._shown.add(key)
                return True
            return False
        return self._apply(text, keep)

    def guard(self, answer: str, question: str) -> tuple[str, Counter]:
        """Defence in depth on the LLM's answer: mask any value it was not shown unmasked and the user
        did not type themselves (hallucinated, memorised, or rebuilt from a masked source)."""
        asked = _keys(question)
        return self._apply(answer, lambda kind, key: kind != "secret" and (key in self._shown or key in asked))

    def _apply(self, text: str, keep: Callable[[str, str], bool]) -> tuple[str, Counter]:
        counts: Counter = Counter()
        for kind, pattern, check in DETECTORS:
            def sub(m: re.Match, kind=kind, check=check) -> str:
                end = check(m)
                if not end:
                    return m[0]
                value = m["v"][:end]
                if keep(kind, _key(kind, value)):
                    return m[0]
                counts[kind] += 1
                whole, start = m[0], m.start("v") - m.start()
                return whole[:start] + self._tag(kind, value) + whole[start + end:]
            text = pattern.sub(sub, text)
        return text, counts

    def _tag(self, kind: str, value: str) -> str:
        if kind == "secret":
            return "[secret]"
        if kind == "dob":
            return "[date of birth]"
        if kind in ("card", "account", "iban"):  # last 4 shown, as PCI DSS allows for cards
            last4 = "".join(c for c in value if c.isalnum())[-4:]
            return f"[{'IBAN' if kind == 'iban' else kind} ending {last4}]"
        if kind == "nric":  # last 3 digits and letter, per PDPC's partial-NRIC guidance
            return f"[NRIC *****{value[-4:].upper()}]"
        numbers = self._numbers[kind]
        return f"[{kind} {numbers.setdefault(_key(kind, value), len(numbers) + 1)}]"


def _keys(text: str) -> set[str]:
    found: set[str] = set()
    Shield()._apply(text, lambda kind, key: found.add(key) or True)
    return found


def mask_secrets(text: str) -> str:
    return Shield()._apply(text, lambda kind, key: kind != "secret")[0]


def for_embedding(text: str) -> str:
    """Everything masked, cut to the model's limit (tags can be longer than what they replace)."""
    return Shield().redact(text, cleared=False)[0][:EMBEDDING_MAX_CHARS]


def has_need_to_know(principals: Iterable[str], need_to_know: object) -> bool:
    """True if one of the user's own platform identities is a handler of the document. Group-like
    principals (`public`, `slack:members`, `google:domain:...`) never count, whatever a connector wrote."""
    if not isinstance(need_to_know, list):
        return False
    held = set(principals)
    return any(isinstance(p, str) and p.startswith(_IDENTITIES) and p in held for p in need_to_know)

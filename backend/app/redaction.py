"""Need-to-Know Shield (ADR-010): deterministic masking of sensitive identifiers wherever document
text leaves our system: the LLM prompt, citation titles and links, the answer, and embeddings.

Authorization decides WHICH documents a user may read (ADR-003); the Shield decides which identifiers
inside them they see. A document's handlers, as its source names them (`metadata.need_to_know`: Jira
assignee and reporter, Drive owners and editors, Confluence owner and author), see it unmasked.
Everyone else sees typed tags. Secrets are masked for everyone, always. Recall over precision: when
in doubt, mask. Stored chunks stay raw; masking happens on the way out.
"""
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from functools import lru_cache

from app.auth.principals import IDENTITY_PREFIX
from app.llm.client import EMBEDDING_MAX_CHARS

_IDENTITIES = tuple(set(IDENTITY_PREFIX.values()))
_CARD_WORD_WINDOW = 30  # characters before a number searched for a card word
_IBAN_LENGTHS = range(15, 35)  # ISO 13616: 15 to 34 characters
_IBAN_MOD = 97  # ISO 7064 MOD 97-10: a valid IBAN leaves remainder 1
_LAST_SHOWN = 4  # characters a tag keeps: last 4 of a card (PCI DSS), last 3 digits and letter of an NRIC (PDPC)
_CHAR_CACHE_SIZE = 1 << 16  # bounded: hostile text can hold every code point
_SENTENCE_END = ",;."  # after normalisation, also the Chinese ，；
_MIN_NAME_PART = 2  # letters a first or last name needs to be masked on its own
_VARIATION_SELECTORS = (("\N{VARIATION SELECTOR-1}", "\N{VARIATION SELECTOR-16}"),
                        ("\N{VARIATION SELECTOR-17}", "\N{VARIATION SELECTOR-256}"))
_CARD_WORD = re.compile(r"(?i)\b(?:card|visa|master ?card|amex|pan|cc|credit|debit)\b|卡")


def _decimals(value: str) -> list[int]:
    return [int(c) for c in value if c.isdecimal()]  # \d is any Unicode decimal; int() reads them all


def _luhn(digits: list[int]) -> bool:
    return sum(d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2)
               for i, d in enumerate(reversed(digits))) % 10 == 0


# Each check returns how many characters of group "v" are sensitive (0: none, leave as is).
def _whole(m: re.Match) -> int:
    return len(m["v"])


def _credential(m: re.Match) -> int:  # an unquoted value ends before the punctuation that ends its sentence
    v = m["v"]
    return len(v) if v[0] in "\"'" else len(v.rstrip(_SENTENCE_END))


def _card(m: re.Match) -> int:  # Luhn-valid, or a card word just before it (a mistyped number)
    near = _CARD_WORD.search(m.string, max(0, m.start() - _CARD_WORD_WINDOW), m.start())
    return len(m["v"]) if _luhn(_decimals(m["v"])) or near else 0


def _iban(m: re.Match) -> int:
    """Longest prefix, ending at a group, that passes mod-97. Prefixes ending in a digit go first: the
    pattern can swallow a following word ("... 32 USD"), and 1 in 97 of those also passes."""
    v = m["v"]
    ends = [len(v)] + [i for i in range(len(v) - 1, 0, -1) if v[i] == " "]
    for end in sorted(ends, key=lambda e: (not v[e - 1].isdigit(), -e)):
        compact = v[:end].replace(" ", "")
        moved = compact[4:] + compact[:4]  # country code and check digits to the end; letters read as base 36
        if len(compact) in _IBAN_LENGTHS and int("".join(str(int(c, 36)) for c in moved)) % _IBAN_MOD == 1:
            return end
    return 0


def _random(m: re.Match) -> int:  # a long run mixing upper case, lower case and digits: a key or token
    v = m["v"]
    word = m.string[max(m.string.rfind(c, 0, m.start("v")) for c in " \t\n") + 1:m.start("v")]
    mixed = any(c.isupper() for c in v) and any(c.islower() for c in v) and any(c.isdigit() for c in v)
    return len(v) if mixed and "://" not in word else 0


def _at_least(n: int, most: float = float("inf")) -> Callable[[re.Match], int]:
    return lambda m: len(m["v"]) if n <= len(_decimals(m["v"])) <= most else 0


# ASCII-only word boundaries. Python's \b and \w count Chinese characters as letters, so "身份证S1234567D"
# would have no boundary before the NRIC and escape. These still keep identifiers glued to ASCII IDs and
# links apart (Slack's /p1727...), and \d still matches any Unicode digit.
_B = r"(?<![A-Za-z0-9_])"
_E = r"(?![A-Za-z0-9_])"
_CJK = "⺀-鿿豈-﫿　-〿＀-￯가-힯"  # Chinese, Japanese, Korean
_COLON = r"[:：]"  # ASCII and full-width
_NUMBER_WORD = rf"(?:\s*(?:no\.?|number|num|#|号码|号))?(?:\s+(?:is|was))?\s*(?:{_COLON}|#)?\s*"  # "account no. is"
_NAME = r"[A-Z][a-zA-Z'’-]+(?:[ \t]+[A-Z][a-zA-Z'’-]+){0,3}"  # capitalised words on one line
_LETTER = rf"[^\W{_CJK}]"  # a letter or digit of any script except CJK (emails may be non-ASCII)

# A person's name: after an honorific or a label only a person carries. A Shield masks every other
# mention of these too (`names_in`).
_PERSON_NAMES = [
    re.compile(r"(?<![A-Za-z])(?:Mr|Mrs|Ms|Mdm|Miss|Madam|Dr|Mx)\.?[ \t]+(?P<v>" + _NAME + ")"),
    re.compile(r"(?i:" + _B + r"(?:customer|customer name|cardholder|card holder|account holder|full name))[ \t]*"
               + _COLON + r"[ \t]*(?P<v>" + _NAME + ")"),
    re.compile(r"(?:姓名|持卡人|客户姓名|客户)[ \t]*" + _COLON + r"[ \t]*(?P<v>[一-鿿]{2,4})"),
]

# (kind, pattern with the sensitive value in group "v", check), applied in this order to the text as the
# model reads it (`_plain_map`); a value one detector masks is blanked for the later ones. Patterns that
# scan runs of characters start with a look-behind, so a long run without a match costs linear time.
DETECTORS: list[tuple[str, re.Pattern, Callable[[re.Match], int]]] = [
    ("secret", re.compile(r"(?P<v>-----BEGIN[A-Z ]*PRIVATE KEY-----.*?(?:-----END[A-Z ]*PRIVATE KEY-----|\Z))",
                          re.S), _whole),
    ("secret", re.compile(_B + r"(?P<v>(?:AKIA|ASIA)[A-Z0-9]{16})" + _E), _whole),
    ("secret", re.compile(_B + r"(?P<v>xox[abposr]-[A-Za-z0-9-]{10,})"), _whole),
    ("secret", re.compile(_B + r"(?P<v>gh[pousr]_[A-Za-z0-9]{30,})"), _whole),
    ("secret", re.compile(_B + r"(?P<v>AIza[0-9A-Za-z_-]{35})"), _whole),
    ("secret", re.compile(_B + r"(?P<v>sk-[A-Za-z0-9_-]{20,})"), _whole),
    ("secret", re.compile(_B + r"(?P<v>eyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]+)"), _whole),
    ("secret", re.compile(r"(?i)" + _B + r"bearer\s+(?P<v>[A-Za-z0-9_.~+/-]{16,}=*)"), _whole),
    # A credential word, alone or ending a name (DB_PASSWORD=, "api_key":, 密码：), then its value. A value
    # that is already a tag is skipped, so text masked once (the question) is unchanged when masked again.
    ("secret", re.compile(r"(?i)(?:(?<![a-z0-9])(?:password|passwd|pwd|passcode|secret|token|"
                          r"(?:api|access|private|encryption|signing)[ _-]?key)(?![a-z0-9])|密码|口令|密钥|令牌)"
                          rf"[\"']?\s*(?:=(?!=)|{_COLON})\s*"  # an assignment, not a comparison (==)
                          rf"(?P<v>(?!\[secret\])(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s{_CJK}]+))"), _credential),
    # Signed-link and OAuth query parameters with no credential word in their name (token= is above).
    ("secret", re.compile(r"(?i)[?&](?:sig|signature|x-amz-signature|x-amz-credential|code)=(?P<v>[^&#\s]+)"),
     _whole),
    # user:pass@ in a URL. The scheme is bounded: unbounded, every word start rescans the rest (quadratic).
    ("secret", re.compile(r"(?i)" + _B + r"[a-z][a-z0-9+.-]{0,30}://[^\s/:@]+:(?P<v>[^\s/@]+)@"), _whole),
    # A whole line of base64 (key material, e.g. the body of a private key whose BEGIN line is elsewhere).
    # Before the next pattern, which would mask only the part of the line before a "/".
    ("secret", re.compile(r"(?m)^[ \t]*(?P<v>[A-Za-z0-9+/]{40,76}={0,2})[ \t]*$"), _random),
    # Any other key or token: 32+ characters mixing cases and digits, then any base64 padding. Not in a
    # link (`_random`): IDs in paths and query strings keep the link working.
    ("secret", re.compile(r"(?<![A-Za-z0-9_+/-])(?P<v>[A-Za-z0-9_+-]{32,}={0,2})"), _random),
    ("iban", re.compile(_B + r"(?P<v>[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30})" + _E), _iban),
    ("card", re.compile(_B + r"(?<!\d)(?P<v>\d(?:[ -]?\d){12,18})(?!\d)"), _card),
    ("card", re.compile(_B + r"(?<!\d)(?P<v>\d{4}\.\d{4,6}\.\d{4,5}(?:\.\d{1,4})?)(?![\d.])"), _card),  # dotted
    ("account", re.compile(r"(?i)(?:" + _B + r"(?:account|acct|a/c)|账号|账户|帐号|帐户|卡号)" + _NUMBER_WORD
                           + r"(?P<v>\d[\d -]{4,24}\d)"), _at_least(6)),
    ("nric", re.compile(r"(?i)" + _B + r"(?P<v>[STFGM]\d{7}[A-Z])" + _E), _whole),
    ("passport", re.compile(r"(?i)(?:" + _B + r"passport|护照)" + _NUMBER_WORD + r"(?P<v>[A-Z]{1,2}\d{6,8}[A-Z]?)"
                            + _E), _whole),
    ("dob", re.compile(r"(?i)(?:" + _B + r"(?:dob|d\.o\.b\.?|date\s+of\s+birth|born(?:\s+on)?)|出生日期|生日)"
                       rf"(?:\s+(?:is|was))?\s*(?:{_COLON}|-)?\s*"
                       r"(?P<v>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月\d{1,2}日?"
                       r"|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})"), _whole),
    ("email", re.compile(rf"(?<!{_LETTER})(?<![.%+-])(?P<v>(?:{_LETTER}|[.%+-]){{1,64}}@(?:{_LETTER}|-)+"
                         rf"(?:\.(?:{_LETTER}|-)+)+)"), _whole),
    ("phone", re.compile(r"(?<![A-Za-z0-9_+])(?P<v>\+\d{1,3}(?:[ .-]?\(?\d{1,4}\)?){2,5})"),
     _at_least(8, 15)),
    ("phone", re.compile(r"(?<![A-Za-z\d_.+/-])(?P<v>(?:\(?65\)?[ -]?)?[3689]\d{3}[ -]?\d{4})"
                         r"(?![A-Za-z\d_]|[.-]\d)"), _whole),
    # Any other number after a phone label, any country's format.
    ("phone", re.compile(r"(?i)(?:" + _B + r"(?:tel|phone|mobile|mob|hp|cell|contact|whatsapp|fax)"
                         r"(?:\s*(?:no\.?|number|#))?|电话|手机|联系电话)"
                         rf"\s*{_COLON}?\s*(?P<v>\+?\(?\d[\d ()./-]{{5,18}}\d)"), _at_least(7, 15)),
    # Names: only where the text says it is a name (label or honorific). Bare names need NER (rejected).
    *(("name", pattern, _whole) for pattern in _PERSON_NAMES),
    # A generic label may name an organisation or project ("Client: DBS Bank", "Project Name: Gateway"):
    # masked where it stands, never propagated.
    ("name", re.compile(r"(?i:" + _B + r"(?:client|applicant|beneficiary|payee|payer|recipient|name))[ \t]*"
                        + _COLON + r"[ \t]*(?P<v>" + _NAME + ")"), _whole),
    ("name", re.compile(r"户名[ \t]*" + _COLON + r"[ \t]*(?P<v>[一-鿿]{2,4})"), _whole),
    # Singapore addresses: postal code, unit number, block number.
    ("address", re.compile(r"(?i)(?:" + _B + r"(?:singapore|s'pore|spore)|新加坡)[ \t,]*\(?(?P<v>\d{6})(?!\d)"),
     _whole),
    ("address", re.compile(r"(?<![A-Za-z0-9#])#(?P<v>\d{1,3}-\d{1,5}[A-Za-z]?)(?![A-Za-z0-9-])"), _whole),
    ("address", re.compile(r"(?i)" + _B + r"blk\.?[ \t]+(?P<v>\d{1,4}[A-Za-z]?)" + _E), _whole),
]


@lru_cache(maxsize=_CHAR_CACHE_SIZE)
def _plain_char(c: str) -> str:
    """A character as the model reads it: format characters (zero-width spaces and joiners) and variation
    selectors (invisible, category Mn, also dropped by the prompt fence) removed, every dash a hyphen,
    everything else in NFKC form (full-width, mathematical, no-break spaces)."""
    category = unicodedata.category(c)
    if category == "Cf" or any(low <= c <= high for low, high in _VARIATION_SELECTORS):
        return ""
    return "-" if category == "Pd" else unicodedata.normalize("NFKC", c)


def _plain_map(text: str) -> tuple[str, Callable[[int, int], tuple[int, int]]]:
    """The text as the model reads it, which the detectors search, and a map from a span in it back to
    the span of `text` it came from, so only masked spans change and the rest stays as written."""
    parts = None if text.isascii() else list(map(_plain_char, text))
    if parts is None or set(map(len, parts)) == {1}:  # nothing dropped or expanded: same offsets
        return text if parts is None else "".join(parts), lambda start, end: (start, end)
    where: list[int] = []  # plain offset -> raw offset, built on the first masked span only

    def to_raw(start: int, end: int) -> tuple[int, int]:
        if not where:
            where.extend(i for i, part in enumerate(parts) for _ in part)
        return where[start], where[end - 1] + 1
    return "".join(parts), to_raw


def _key(kind: str, value: str) -> str:
    """Comparable form of a value: emails by address, everything else without separators or case."""
    return value.lower() if kind == "email" else re.sub(r"[\W_]", "", value.lower())


def _plain_name(name: str) -> str:
    return _key("name", re.sub(r"\s*\(.*\)\s*$", "", name))  # "Alice Tan (payments engineer)" -> "alicetan"


def _name_parts(name: str) -> list[str]:
    """The first, last and middle names that can stand for `name` on their own."""
    parts = re.sub(r"\s*\(.*\)\s*$", "", name).split()
    return [p for p in parts if len(p) >= _MIN_NAME_PART] if len(parts) > 1 else []


def names_in(texts: Iterable[str]) -> dict[str, str]:
    """Every person's name in `texts` (after an honorific or a person label), and each of its parts, mapped
    to the full name. A Shield that knows them masks every other mention, labelled or not."""
    found = [m["v"] for text in texts for pattern in _PERSON_NAMES for m in pattern.finditer(_plain_map(text)[0])]
    names: dict[str, str] = {}
    for name in found:
        names.setdefault(name, name)
    for name in found:
        for part in _name_parts(name):
            names.setdefault(part, name)
    return names


class Shield:
    """One per question, so the same value gets the same tag in every source, and the answer guard
    knows which values were shown unmasked."""

    def __init__(self, colleagues: Iterable[str] = (), colleague_names: Iterable[str] = ()):
        # The asker's company's users: their emails and names are not masked.
        self.colleagues = {e.lower() for e in colleagues}
        colleague_names = [n for n in colleague_names if n]
        self.colleague_names = {_plain_name(n) for n in colleague_names}
        self._colleague_parts = {_key("name", p) for n in colleague_names for p in _name_parts(n)}
        self._names: dict[str, str] = {}  # a known name, or a part of one, -> the full name
        self._known: list[tuple[str, re.Pattern, Callable[[re.Match], int]]] = []
        self._numbers: dict[str, dict[str, int]] = defaultdict(dict)
        self._shown: dict[str, tuple[str, str]] = {}  # key -> (kind, value) of each value left unmasked

    def know(self, names: dict[str, str]) -> None:
        """Mask these names (from `names_in`) wherever they appear, with or without a label. A colleague's
        name, or a part of one, stays visible."""
        for value, full in names.items():
            if _plain_name(full) not in self.colleague_names and _key("name", value) not in self._colleague_parts:
                self._names.setdefault(value, full)
        alternatives = "|".join(map(re.escape, sorted(self._names, key=len, reverse=True)))
        self._known = [("name", re.compile(_B + f"(?P<v>{alternatives})" + _E), _whole)] if self._names else []

    def _canonical(self, kind: str, value: str) -> str:
        """The key a value is compared and numbered by; a first or last name counts as its full name."""
        return _key(kind, self._names.get(value, value) if kind == "name" else value)

    def redact(self, text: str, cleared: bool) -> tuple[str, Counter]:
        """Mask `text` for this reader. `cleared` (need-to-know): only secrets are masked."""
        def keep(kind: str, value: str) -> bool:
            key = self._canonical(kind, value)
            if kind != "secret" and (cleared or kind == "email" and key in self.colleagues
                                     or kind == "name" and key in self.colleague_names):
                self._shown.setdefault(_key(kind, value), (kind, value))
                self._shown.setdefault(key, (kind, value))
                return True
            return False
        return self._apply(text, keep)

    def guard(self, answer: str, question: str) -> tuple[str, Counter]:
        """Defence in depth on the LLM's answer: mask any value it was not shown unmasked and the user
        did not type themselves (hallucinated, memorised, or rebuilt from a masked source)."""
        asked = _keys(question, self._known)
        return self._apply(answer, lambda kind, value: kind != "secret" and (
            (key := self._canonical(kind, value)) in self._shown or key in asked or _key(kind, value) in asked))

    def mask_all(self, text: str) -> str:
        """Everything masked, for the audit log: what the detectors find, and every value this Shield left
        unmasked, wherever it appears again ("customer Jane Lee" in an answer has no label to detect)."""
        by_kind = defaultdict(set)
        for kind, value in self._shown.values():
            by_kind[kind].add(re.escape(value))
        shown = [(kind, re.compile(_B + f"(?P<v>{'|'.join(sorted(values, key=len, reverse=True))})" + _E), _whole)
                 for kind, values in by_kind.items()]
        return self._apply(text, lambda kind, value: False, shown)[0]

    def _apply(self, text: str, keep: Callable[[str, str], bool],
               extra: Iterable[tuple[str, re.Pattern, Callable[[re.Match], int]]] = ()) -> tuple[str, Counter]:
        plain, to_raw = _plain_map(text)
        masked = bytearray(len(plain))  # 1 where an earlier detector masked a value
        spans: list[tuple[int, int, str]] = []
        counts: Counter = Counter()
        for kind, pattern, check in (*DETECTORS, *self._known, *extra):
            found = []
            for m in pattern.finditer(plain):
                length = check(m)
                start, end = m.start("v"), m.start("v") + length
                if not length or masked.find(1, start, end) >= 0 or keep(kind, value := m["v"][:length]):
                    continue
                counts[kind] += 1
                found.append((start, end, self._tag(kind, value)))
            pieces, pos = [], 0
            for start, end, _ in found:  # later detectors see a masked value as blank, as they would a tag
                masked[start:end] = b"\x01" * (end - start)
                pieces += [plain[pos:start], "\0" * (end - start)]
                pos = end
            plain = "".join(pieces) + plain[pos:]
            spans += found
        out, pos = [], 0
        for start, end, tag in sorted(spans):
            start, end = to_raw(start, end)
            out += [text[pos:max(start, pos)], tag]
            pos = max(end, pos)
        return "".join(out) + text[pos:], counts

    def _tag(self, kind: str, value: str) -> str:
        if kind == "secret":
            return "[secret]"
        if kind in ("dob", "address"):
            return "[date of birth]" if kind == "dob" else "[address]"
        if kind in ("card", "account", "iban"):  # last 4 shown, as PCI DSS allows for cards
            last = "".join(c for c in value if c.isalnum())[-_LAST_SHOWN:]
            return f"[{'IBAN' if kind == 'iban' else kind} ending {last}]"
        if kind == "nric":  # last 3 digits and letter, per PDPC's partial-NRIC guidance
            return f"[NRIC *****{value[-_LAST_SHOWN:].upper()}]"
        numbers = self._numbers[kind]
        return f"[{kind} {numbers.setdefault(self._canonical(kind, value), len(numbers) + 1)}]"


def _keys(text: str, extra: Iterable[tuple[str, re.Pattern, Callable[[re.Match], int]]] = ()) -> set[str]:
    found: set[str] = set()
    Shield()._apply(text, lambda kind, value: found.add(_key(kind, value)) or True, extra)
    return found


def mask_secrets(text: str) -> str:
    return Shield()._apply(text, lambda kind, value: kind != "secret")[0]


def for_embedding(text: str, names: dict[str, str] | None = None) -> str:
    """Everything masked, cut to the model's limit (tags can be longer than what they replace). `names`:
    from `names_in` over the whole document, so a name labelled in another chunk is masked here too."""
    shield = Shield()
    shield.know(names_in([text]) if names is None else names)
    return shield.redact(text, cleared=False)[0][:EMBEDDING_MAX_CHARS]


def protected_spans(text: str) -> list[tuple[int, int]]:
    """Where anything that could be an identifier sits, with its label and the characters before it that may
    hold a card word: places a chunk must not be cut, or half of a card number, or a label without its value,
    would reach different chunks. Found in the text as the model reads it, returned as offsets in `text`."""
    plain, to_raw = _plain_map(text)
    return sorted(to_raw(max(0, m.start() - _CARD_WORD_WINDOW), m.end())
                  for _, pattern, _ in DETECTORS for m in pattern.finditer(plain))


def has_need_to_know(principals: Iterable[str], need_to_know: object) -> bool:
    """True if one of the user's own platform identities is a handler of the document. Group-like
    principals (`public`, `slack:members`, `google:domain:...`) never count, whatever a connector wrote."""
    if not isinstance(need_to_know, list):
        return False
    held = set(principals)
    return any(isinstance(p, str) and p.startswith(_IDENTITIES) and p in held for p in need_to_know)

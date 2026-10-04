"""Live permission check (ADR-003): the source platform has the final say.

Each connector provides `can_read(principal, ids) -> {id: bool}` (see
docs/connectors/). Before anything reaches the LLM, every candidate is checked
with its source, in parallel, with a timeout. Deny by default: a False, a
missing answer, an error or a timeout all drop the document.
"""
import logging
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Protocol

from app.auth.principals import identity_for

log = logging.getLogger(__name__)

CanRead = Callable[[str, list[str]], Mapping[str, bool]]
DEFAULT_TIMEOUT_S = 2.0


class CandidateLike(Protocol):
    document_id: int
    source: str
    source_id: str
    acl: list[str]


@dataclass(frozen=True)
class Decision:
    document_id: int
    allowed: bool
    reason: str


def live_check(
    candidates: Sequence[CandidateLike],
    principals: list[str],
    checkers: Mapping[str, CanRead],
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[Decision]:
    """Return one Decision per candidate, in the same order."""
    decisions: dict[int, Decision] = {}
    by_source: dict[str, list[CandidateLike]] = defaultdict(list)
    for c in candidates:
        by_source[c.source].append(c)

    def deny_all(cands: list[CandidateLike], reason: str) -> None:
        for c in cands:
            decisions[c.document_id] = Decision(c.document_id, False, reason)

    pool = ThreadPoolExecutor(max_workers=max(1, len(by_source)))
    futures = {}
    try:
        for source, cands in by_source.items():
            identity = identity_for(principals, source)
            checker = checkers.get(source)
            if identity is None:
                deny_all(cands, f"no linked {source} account")
            elif checker is None:
                deny_all(cands, f"no live check available for {source}")
            else:
                ids = [c.source_id for c in cands]
                futures[pool.submit(checker, identity, ids)] = (source, cands)

        done, _ = wait(futures, timeout=timeout_s)
        for future, (source, cands) in futures.items():
            if future not in done:
                deny_all(cands, f"{source} live check timed out")
                continue
            # Everything about this source's answer is inside the try: a bad reply
            # denies this source's documents and never fails the whole request.
            try:
                answers = future.result()
                if not isinstance(answers, Mapping):
                    log.warning("live check for %s returned %s, not a mapping", source, type(answers).__name__)
                    deny_all(cands, f"{source} live check gave an invalid reply")
                    continue
                for c in cands:
                    if answers.get(c.source_id) is True:
                        decisions[c.document_id] = Decision(c.document_id, True, f"allowed by {source} check")
                    else:
                        decisions[c.document_id] = Decision(c.document_id, False, f"denied by {source} check")
            except Exception as exc:  # any failure denies
                log.warning("live check for %s failed: %s", source, exc)
                deny_all(cands, f"{source} live check failed ({type(exc).__name__})")
    finally:
        # Do not wait for a hung checker: its documents are already denied.
        pool.shutdown(wait=False, cancel_futures=True)

    return [decisions[c.document_id] for c in candidates]


# --- STUB ---------------------------------------------------------------------
# Until the connectors' real can_read functions exist (roadmap Task 1), this
# answers from the STORED acl, not from the live platform. It therefore does
# NOT catch revocations that happened after the last sync. Replace each entry
# in default_checkers with the connector's can_read as it lands.

STUB_MODE = "stub: stored ACL, not live"


def stored_acl_stub(candidates: Sequence[CandidateLike], principals: list[str]) -> CanRead:
    held = set(principals)
    acl_by_id = {c.source_id: set(c.acl) for c in candidates}

    def can_read(_principal: str, ids: list[str]) -> dict[str, bool]:
        return {i: bool(acl_by_id.get(i, set()) & held) for i in ids}

    return can_read


def default_checkers(candidates: Sequence[CandidateLike], principals: list[str]) -> dict[str, CanRead]:
    log.warning("live check is using the STUB (%s)", STUB_MODE)
    return {
        source: stored_acl_stub([c for c in candidates if c.source == source], principals)
        for source in ("slack", "drive")
    }


default_checkers.mode = STUB_MODE  # recorded in the audit log

"""Query pipeline: question -> permission-filtered search -> live check -> LLM -> audit.

Security boundary (ARCHITECTURE.md section 1): nothing reaches the LLM unless
it passed the stored-ACL filter, the admin boundary AND the live check. When
nothing passes, the LLM is not called at all.

No database connection is held during the slow external calls (embedding, live
check, LLM): the database is used in two short transactions.
"""
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.audit.log import record_event
from app.auth.live_check import CanRead, default_checkers, live_check
from app.auth.principals import principals_for
from app.auth.session import User
from app.db import Tx
from app.llm.client import ChatResult
from app.llm.grounding import FALLBACK_ANSWER, SourceBlock, build_messages, ground
from app.retrieval.search import Candidate, ChunkHit, hybrid_search, restricted_matches

log = logging.getLogger(__name__)

MAX_DOCS_TO_LLM = 10
MAX_CONTEXT_CHARS = 12_000  # ~3k tokens: prompt size drives LLM latency
UNAVAILABLE_ANSWER = "The assistant is unavailable right now. Please try again shortly."

CheckersFactory = Callable[[Sequence[Candidate], list[str]], Mapping[str, CanRead]]


class LLM(Protocol):
    def chat(self, messages: list[dict]) -> ChatResult: ...
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class Citation:
    id: str
    title: str
    url: str
    source: str
    updated_at: datetime
    synced_at: datetime | None


@dataclass(frozen=True)
class QueryResult:
    answer: str
    citations: list[Citation]
    audit_id: int


def _fit(candidates: list[Candidate]) -> list[tuple[Candidate, list[ChunkHit]]]:
    """Best-ranked documents, each with its best chunks, until MAX_CONTEXT_CHARS is used up."""
    budget, picked = MAX_CONTEXT_CHARS, []
    for c in candidates[:MAX_DOCS_TO_LLM]:
        kept = []
        for ch in c.chunks:  # best first
            if len(ch.text) <= budget:
                kept.append(ch)
                budget -= len(ch.text)
        if kept:
            picked.append((c, kept))
    return picked


def answer_question(
    tx: Tx,
    user: User,
    question: str,
    llm: LLM,
    checkers_factory: CheckersFactory = default_checkers,
    live_check_timeout_s: float = 2.0,
) -> QueryResult:
    audit: dict = {
        "user_email": user.email,
        "role": "admin" if user.is_admin else "user",
        "question": question,
        "live_check_mode": getattr(checkers_factory, "mode", "connector checks"),
    }

    # 1. Embed the question; fall back to keyword-only search if that fails.
    embedding = None
    try:
        embedding = llm.embed([question])[0]
        audit["search_mode"] = "hybrid"
    except Exception as exc:
        log.warning("question embedding failed, using keyword search only: %s", exc)
        audit["search_mode"] = "keyword_only"
        audit["embedding_error"] = type(exc).__name__

    with tx() as conn:
        # 2. Search only documents the user's stored ACL and the boundary allow.
        principals = audit["principals"] = principals_for(conn, user.id)
        candidates = hybrid_search(conn, user.company_id, principals, question, embedding)

        # AUDIT ONLY (ADR-007): restricted documents this question would have reached.
        # Runs in a savepoint so a failure here cannot lose the audit event itself.
        try:
            with conn.begin_nested():
                audit["restricted_matches"] = restricted_matches(conn, user.company_id, principals, question)
        except Exception as exc:
            log.error("restricted-match audit search failed: %s", exc)
            audit["restricted_matches_error"] = type(exc).__name__

    # 3. Live check with each source; anything not confirmed is dropped.
    decisions = live_check(candidates, principals, checkers_factory(candidates, principals), live_check_timeout_s)
    audit["candidates"] = [
        {"document": c.key, "allowed": d.allowed, "reason": d.reason} for c, d in zip(candidates, decisions)
    ]
    sources = _fit([c for c, d in zip(candidates, decisions) if d.allowed])
    audit["sent_to_llm"] = [c.key for c, _ in sources]

    citations: list[Citation] = []
    if not sources:
        # Same reply whether nothing exists or nothing is permitted (INV-5).
        answer = FALLBACK_ANSWER
        audit["llm_called"] = False
    else:
        by_label = {f"S{i}": c for i, (c, _) in enumerate(sources, start=1)}
        blocks = [
            SourceBlock(
                label=label,
                platform=c.source,
                title=c.title,
                updated_at=c.updated_at.isoformat(),
                text="\n...\n".join(ch.text for ch in sorted(chunks, key=lambda ch: ch.ordinal)),
            )
            for label, (c, chunks) in zip(by_label, sources)
        ]
        audit["llm_called"] = True
        try:
            result = llm.chat(build_messages(question, blocks))
        except Exception as exc:
            log.error("LLM call failed: %s", exc)
            answer = UNAVAILABLE_ANSWER
            audit["llm_error"] = type(exc).__name__
        else:
            grounded = ground(result.content, set(by_label))
            answer = grounded.answer
            citations = [
                Citation(c.key, c.title, c.url, c.source, c.updated_at, c.synced_at)
                for c in (by_label[label] for label in grounded.labels)
            ]
            audit.update(
                model=result.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                removed_citations=grounded.removed_labels,  # labels the model invented
                grounding_note=grounded.note,
            )

    audit["answer"] = answer
    audit["citations"] = [c.id for c in citations]
    with tx() as conn:  # committed before the answer is returned
        audit_id = record_event(conn, user.id, "query", audit)
    return QueryResult(answer=answer, citations=citations, audit_id=audit_id)

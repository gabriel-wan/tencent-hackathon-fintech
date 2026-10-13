"""Hybrid search over chunks, restricted to documents the user may see (ADR-005).

The permission filter (ACL overlaps the user's principals) and the admin
boundary are applied in the first CTE, before any ranking. Denied documents
are never returned or counted. They can nudge the order of permitted ones:
BM25 term statistics (IDF, average length) are index-wide, so every company's
and every restricted chunk counts. Scores are never shown; accepted in ADR-012
(SECURITY.md INV-5, T9).
Keyword (BM25, ParadeDB's pg_search) and semantic (pgvector) ranks are merged with
reciprocal rank fusion (ADR-012). This is the fast pre-filter only; the live check
(app/auth/live_check.py) has the final say.

`restricted_matches` is an AUDIT-ONLY search without the filter (ADR-007): it
records which restricted documents a question would have reached. Its results
must never be returned to the user or sent to the LLM.
"""
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Connection, text

RRF_K = 60  # equal weights: 0.7 vector / 0.3 keyword measured worse with BM25 (ADR-012)

_SEARCH_TEMPLATE = """
    WITH pool AS (
        {pool}
    ),
    kw AS (
        -- BM25 over title, headings and text (ADR-012): ANY meaningful word of the question matches,
        -- rare words count for more; stemmed, English stop words ignored.
        SELECT id, row_number() OVER (ORDER BY score DESC, id) AS r
        FROM (
            SELECT c.id, paradedb.score(c.id) AS score
            FROM chunks c
            JOIN pool p ON p.id = c.document_id
            WHERE c.search ||| :question
            ORDER BY score DESC, c.id
            LIMIT :chunk_limit
        ) best
    ),
    vec AS (
        -- Inner ORDER BY distance + LIMIT is the shape the HNSW index can serve.
        SELECT id, row_number() OVER (ORDER BY dist, id) AS r
        FROM (
            SELECT c.id, c.embedding <=> CAST(:qvec AS vector) AS dist
            FROM chunks c
            JOIN pool p ON p.id = c.document_id
            WHERE :use_vec AND c.embedding IS NOT NULL
            ORDER BY dist
            LIMIT :chunk_limit
        ) nearest
    ),
    fused AS (
        SELECT id, CAST(sum(1.0 / (:rrf_k + r)) AS double precision) AS score
        FROM (SELECT id, r FROM kw UNION ALL SELECT id, r FROM vec) ranked
        GROUP BY id
    )
    SELECT f.score, c.id AS chunk_id, c.ordinal, c.text,
           d.id AS document_id, d.source, d.source_id, d.title, d.url, d.updated_at, d.acl,
           d.metadata -> 'need_to_know' AS need_to_know,
           EXISTS (
               SELECT 1 FROM boundary b
               WHERE b.company_id = d.company_id AND b.source = d.source AND b.scope_id = d.scope_id
           ) AS in_boundary,
           s.updated_at AS synced_at
    FROM fused f
    JOIN chunks c ON c.id = f.id
    JOIN documents d ON d.id = c.document_id
    LEFT JOIN sync_state s ON s.company_id = d.company_id AND s.source = d.source AND s.key = d.scope_id
    ORDER BY f.score DESC, c.id
"""

# What the user may see: their own company's documents only (principals such as
# `public` and `slack:members` are held in every company), not deleted, ACL
# overlap, inside the admin boundary.
_PERMITTED_POOL = """
        SELECT d.id
        FROM documents d
        WHERE d.company_id = :company_id
          AND d.deleted_at IS NULL
          AND d.acl && CAST(:principals AS text[])
          AND EXISTS (
              SELECT 1 FROM boundary b
              WHERE b.company_id = d.company_id AND b.source = d.source AND b.scope_id = d.scope_id
          )
"""

# AUDIT ONLY: live documents of the user's company they may NOT see (the exact
# complement of _PERMITTED_POOL within the company). Searching only these means
# documents the user can see never crowd restricted ones out of the results.
# Other companies' documents are never searched, not even for the audit.
_RESTRICTED_POOL = """
        SELECT d.id
        FROM documents d
        WHERE d.company_id = :company_id
          AND d.deleted_at IS NULL
          AND NOT (
              d.acl && CAST(:principals AS text[])
              AND EXISTS (
                  SELECT 1 FROM boundary b
                  WHERE b.company_id = d.company_id AND b.source = d.source AND b.scope_id = d.scope_id
              )
          )
"""

SEARCH_SQL = text(_SEARCH_TEMPLATE.format(pool=_PERMITTED_POOL))
_AUDIT_ONLY_SQL = text(_SEARCH_TEMPLATE.format(pool=_RESTRICTED_POOL))


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    ordinal: int
    text: str
    score: float


@dataclass
class Candidate:
    document_id: int
    source: str
    source_id: str
    title: str
    url: str
    updated_at: datetime
    acl: list[str]
    score: float
    in_boundary: bool = True
    synced_at: datetime | None = None  # its scope's last complete sync
    need_to_know: object = None  # metadata.need_to_know as stored: checked by app.redaction.has_need_to_know
    chunks: list[ChunkHit] = field(default_factory=list)
    neighbours: list[ChunkHit] = field(default_factory=list)  # the chunks next to its hits (add_neighbours)

    @property
    def key(self) -> str:
        """Stable, human-readable document ID used in citations and the audit log."""
        return f"{self.source}:{self.source_id}"


def vector_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(format(float(x), ".8g") for x in vec) + "]"


def _ranked(
    conn: Connection,
    sql,
    company_id: int,
    principals: list[str],
    question: str,
    question_embedding: Sequence[float] | None,
    chunk_limit: int,
    doc_limit: int,
    chunks_per_doc: int,
) -> list[Candidate]:
    # With an HNSW index, filtered vector search stops after `ef_search` nearest
    # chunks; if most belong to documents the user may not see, too few results
    # come back. Iterative scan keeps searching until the LIMIT is met (pgvector
    # 0.8+). SET LOCAL lasts only until the end of the current transaction.
    conn.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = conn.execute(
        sql,
        {
            "company_id": company_id,
            "principals": list(principals),
            "question": question,
            "qvec": vector_literal(question_embedding) if question_embedding is not None else None,
            "use_vec": question_embedding is not None,
            "chunk_limit": chunk_limit,
            "rrf_k": RRF_K,
        },
    ).mappings().all()

    docs: dict[int, Candidate] = {}
    for row in rows:  # already ordered by score, best first
        doc = docs.get(row["document_id"])
        if doc is None:
            if len(docs) >= doc_limit:
                continue
            doc = docs[row["document_id"]] = Candidate(
                document_id=row["document_id"],
                source=row["source"],
                source_id=row["source_id"],
                title=row["title"],
                url=row["url"],
                updated_at=row["updated_at"],
                acl=list(row["acl"]),
                score=row["score"],
                in_boundary=row["in_boundary"],
                synced_at=row["synced_at"],
                need_to_know=row["need_to_know"],
            )
        if len(doc.chunks) < chunks_per_doc:
            doc.chunks.append(ChunkHit(row["chunk_id"], row["ordinal"], row["text"], row["score"]))
    return list(docs.values())


def hybrid_search(
    conn: Connection,
    company_id: int,
    principals: list[str],
    question: str,
    question_embedding: Sequence[float] | None = None,
    chunk_limit: int = 50,
    doc_limit: int = 20,
    chunks_per_doc: int = 3,
) -> list[Candidate]:
    """Documents the user may see, best first. This is what can reach the LLM."""
    return _ranked(conn, SEARCH_SQL, company_id, principals, question, question_embedding,
                   chunk_limit, doc_limit, chunks_per_doc)


def add_neighbours(conn: Connection, candidates: list[Candidate]) -> None:
    """Fills each candidate's `neighbours`: the chunks just before and after its hits that are not hits
    themselves (ADR-012), so a small chunk reaches the LLM with the text around it. Reads only documents
    already in `candidates`, which the permission filter let through; the live check still decides."""
    hits = {(c.document_id, ch.ordinal) for c in candidates for ch in c.chunks}
    wanted = {(d, o + step) for d, o in hits for step in (-1, 1)} - hits
    if not wanted:
        return
    docs, ordinals = zip(*wanted)
    by_doc = {c.document_id: c for c in candidates}
    for row in conn.execute(text(
            "SELECT c.id, c.document_id, c.ordinal, c.text FROM chunks c "
            "JOIN unnest(CAST(:d AS bigint[]), CAST(:o AS integer[])) AS w(document_id, ordinal) "
            "ON w.document_id = c.document_id AND w.ordinal = c.ordinal ORDER BY c.ordinal"),
            {"d": list(docs), "o": list(ordinals)}):
        by_doc[row.document_id].neighbours.append(ChunkHit(row.id, row.ordinal, row.text, 0.0))


def restricted_matches(
    conn: Connection,
    company_id: int,
    principals: list[str],
    question: str,
    doc_limit: int = 20,
) -> list[dict[str, str]]:
    """AUDIT ONLY: restricted documents the question matched by keyword.

    Returns document keys and the reason the user could not see them. Never
    return these to the user or put them in an LLM prompt.

    Keyword matches only, on purpose: semantic search always returns the
    nearest documents, relevant or not, which would record a user as having
    "reached" restricted documents unrelated to their question. A missed
    paraphrase is a smaller harm than a false accusation in an audit log.
    """
    held = set(principals)
    matches = []
    for c in _ranked(conn, _AUDIT_ONLY_SQL, company_id, principals, question, None,
                     chunk_limit=50, doc_limit=doc_limit, chunks_per_doc=1):
        reasons = []
        if not held & set(c.acl):
            reasons.append("user not in document ACL")
        if not c.in_boundary:
            reasons.append("outside admin boundary")
        if reasons:
            matches.append({"document": c.key, "reason": "; ".join(reasons)})
    return matches

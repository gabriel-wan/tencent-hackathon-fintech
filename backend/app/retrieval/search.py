"""Hybrid search over chunks, restricted to documents the user may see (ADR-005).

The permission filter (ACL overlaps the user's principals) and the admin
boundary are applied in the first CTE, before any ranking. Denied documents
therefore never influence ranking or result counts (SECURITY.md INV-5).
Keyword (Postgres full-text) and semantic (pgvector) ranks are merged with
reciprocal rank fusion. This is the fast pre-filter only; the live check
(app/auth/live_check.py) has the final say.

`restricted_matches` is an AUDIT-ONLY search without the filter (ADR-007): it
records which restricted documents a question would have reached. Its results
must never be returned to the user or sent to the LLM.
"""
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Connection, text

RRF_K = 60

_SEARCH_TEMPLATE = """
    WITH pool AS (
        {pool}
    ),
    q AS (
        -- Natural-language questions: match ANY meaningful word, rank by coverage.
        SELECT to_tsquery(
            'english',
            replace(CAST(plainto_tsquery('english', :question) AS text), ' & ', ' | ')
        ) AS query
    ),
    kw AS (
        SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q.query) DESC, c.id) AS r
        FROM chunks c
        JOIN pool p ON p.id = c.document_id
        CROSS JOIN q
        WHERE c.tsv @@ q.query
        ORDER BY r
        LIMIT :chunk_limit
    ),
    vec AS (
        SELECT c.id,
               row_number() OVER (ORDER BY c.embedding <=> CAST(:qvec AS vector), c.id) AS r
        FROM chunks c
        JOIN pool p ON p.id = c.document_id
        WHERE :use_vec AND c.embedding IS NOT NULL
        ORDER BY r
        LIMIT :chunk_limit
    ),
    fused AS (
        SELECT id, CAST(sum(1.0 / (:rrf_k + r)) AS double precision) AS score
        FROM (SELECT id, r FROM kw UNION ALL SELECT id, r FROM vec) ranked
        GROUP BY id
    )
    SELECT f.score, c.id AS chunk_id, c.ordinal, c.text,
           d.id AS document_id, d.source, d.source_id, d.title, d.url, d.updated_at, d.acl,
           EXISTS (
               SELECT 1 FROM boundary b WHERE b.source = d.source AND b.scope_id = d.scope_id
           ) AS in_boundary
    FROM fused f
    JOIN chunks c ON c.id = f.id
    JOIN documents d ON d.id = c.document_id
    ORDER BY f.score DESC, c.id
"""

# What the user may see: not deleted, ACL overlap, inside the admin boundary.
_PERMITTED_POOL = """
        SELECT d.id
        FROM documents d
        WHERE d.deleted_at IS NULL
          AND d.acl && CAST(:principals AS text[])
          AND EXISTS (
              SELECT 1 FROM boundary b
              WHERE b.source = d.source AND b.scope_id = d.scope_id
          )
"""

# AUDIT ONLY: every live document, regardless of permissions.
_UNFILTERED_POOL = """
        SELECT d.id FROM documents d WHERE d.deleted_at IS NULL
"""

SEARCH_SQL = text(_SEARCH_TEMPLATE.format(pool=_PERMITTED_POOL))
_AUDIT_ONLY_SQL = text(_SEARCH_TEMPLATE.format(pool=_UNFILTERED_POOL))


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
    chunks: list[ChunkHit] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable, human-readable document ID used in citations and the audit log."""
        return f"{self.source}:{self.source_id}"


def vector_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(format(float(x), ".8g") for x in vec) + "]"


def _ranked(
    conn: Connection,
    sql,
    principals: list[str],
    question: str,
    question_embedding: Sequence[float] | None,
    chunk_limit: int,
    doc_limit: int,
    chunks_per_doc: int,
) -> list[Candidate]:
    rows = conn.execute(
        sql,
        {
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
            )
        if len(doc.chunks) < chunks_per_doc:
            doc.chunks.append(ChunkHit(row["chunk_id"], row["ordinal"], row["text"], row["score"]))
    return list(docs.values())


def hybrid_search(
    conn: Connection,
    principals: list[str],
    question: str,
    question_embedding: Sequence[float] | None = None,
    chunk_limit: int = 50,
    doc_limit: int = 20,
    chunks_per_doc: int = 3,
) -> list[Candidate]:
    """Documents the user may see, best first. This is what can reach the LLM."""
    return _ranked(conn, SEARCH_SQL, principals, question, question_embedding,
                   chunk_limit, doc_limit, chunks_per_doc)


def restricted_matches(
    conn: Connection,
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
    for c in _ranked(conn, _AUDIT_ONLY_SQL, principals, question, None,
                     chunk_limit=50, doc_limit=doc_limit, chunks_per_doc=1):
        reasons = []
        if not held & set(c.acl):
            reasons.append("user not in document ACL")
        if not c.in_boundary:
            reasons.append("outside admin boundary")
        if reasons:
            matches.append({"document": c.key, "reason": "; ".join(reasons)})
    return matches

"""Hybrid search over chunks, restricted to documents the user may see (ADR-005).

The permission filter (ACL overlaps the user's principals) and the admin
boundary are applied in the first CTE, before any ranking. Denied documents
therefore never influence ranking or result counts (SECURITY.md INV-5).
Keyword (Postgres full-text) and semantic (pgvector) ranks are merged with
reciprocal rank fusion. This is the fast pre-filter only; the live check
(app/auth/live_check.py) has the final say.
"""
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Connection, text

RRF_K = 60

SEARCH_SQL = text(
    """
    WITH allowed AS (
        SELECT d.id
        FROM documents d
        WHERE d.deleted_at IS NULL
          AND d.acl && CAST(:principals AS text[])
          AND EXISTS (
              SELECT 1 FROM boundary b
              WHERE b.source = d.source AND b.scope_id = d.scope_id
          )
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
        JOIN allowed a ON a.id = c.document_id
        CROSS JOIN q
        WHERE c.tsv @@ q.query
        ORDER BY r
        LIMIT :chunk_limit
    ),
    vec AS (
        SELECT c.id,
               row_number() OVER (ORDER BY c.embedding <=> CAST(:qvec AS vector), c.id) AS r
        FROM chunks c
        JOIN allowed a ON a.id = c.document_id
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
           d.id AS document_id, d.source, d.source_id, d.title, d.url, d.updated_at, d.acl
    FROM fused f
    JOIN chunks c ON c.id = f.id
    JOIN documents d ON d.id = c.document_id
    ORDER BY f.score DESC, c.id
    """
)


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
    chunks: list[ChunkHit] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable, human-readable document ID used in citations and the audit log."""
        return f"{self.source}:{self.source_id}"


def vector_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(format(float(x), ".8g") for x in vec) + "]"


def hybrid_search(
    conn: Connection,
    principals: list[str],
    question: str,
    question_embedding: Sequence[float] | None = None,
    chunk_limit: int = 50,
    doc_limit: int = 20,
    chunks_per_doc: int = 3,
) -> list[Candidate]:
    rows = conn.execute(
        SEARCH_SQL,
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
            )
        if len(doc.chunks) < chunks_per_doc:
            doc.chunks.append(ChunkHit(row["chunk_id"], row["ordinal"], row["text"], row["score"]))
    return list(docs.values())

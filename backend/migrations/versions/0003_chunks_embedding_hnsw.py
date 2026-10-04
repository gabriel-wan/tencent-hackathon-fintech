"""HNSW index on chunks.embedding for semantic search (cosine distance)

Used by the `ORDER BY embedding <=> query LIMIT n` in app/retrieval/search.py.
Searches run with `hnsw.iterative_scan` on, so the permission filter (a join
on allowed documents) cannot starve the results.
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw_idx ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS chunks_embedding_hnsw_idx")

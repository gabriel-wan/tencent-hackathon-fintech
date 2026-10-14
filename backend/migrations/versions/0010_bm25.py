"""BM25 keyword search over each chunk's title, headings and text (ADR-012), with ParadeDB's pg_search

- The database image moves from pgvector/pgvector to paradedb/paradedb (same Postgres 17 and pgvector, plus
  pg_search). Its newer C library sorts text differently: when the database records an older collation version,
  every index is rebuilt and the version refreshed, or an index on text could silently miss rows. template1 is
  refreshed too, so CREATE DATABASE (tests, evaluation) keeps working; it holds no indexes of ours.
- chunks.context: the title and the headings a chunk sits under, written by the sync worker (app/sync.py) and the
  seed. Existing chunks get their document's title; migration 0009 has the worker rewrite synced ones.
- chunks.search: context and text together, the one field the BM25 index searches, so a ticket key or a page title
  finds its chunks. English stemming and stop words: "refunds" finds "refund", and a question of stop words matches
  nothing, so the audit-only restricted search (ADR-007) records no document for "the".
- The full-text column tsv and its index go: nothing reads them any more.
"""
from alembic import op
from sqlalchemy import text

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TOKENIZER = '{"search": {"tokenizer": {"type": "default", "stemmer": "English", "stopwords_language": "English"}}}'


def _refresh_collations() -> None:
    db = op.get_bind().execute(text(
        "SELECT quote_ident(datname) FROM pg_database WHERE datname = current_database() "
        "AND datcollversion IS DISTINCT FROM pg_database_collation_actual_version(oid)")).scalar()
    with op.get_context().autocommit_block():  # REINDEX DATABASE cannot run in a transaction
        if db:
            op.execute(f"REINDEX DATABASE {db}")
            op.execute(f"ALTER DATABASE {db} REFRESH COLLATION VERSION")
        if op.get_bind().execute(text(
                "SELECT datcollversion IS DISTINCT FROM pg_database_collation_actual_version(oid) "
                "FROM pg_database WHERE datname = 'template1'")).scalar():
            op.execute("ALTER DATABASE template1 REFRESH COLLATION VERSION")


def upgrade():
    _refresh_collations()
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
    op.execute("ALTER TABLE chunks ADD COLUMN context text NOT NULL DEFAULT ''")
    op.execute("UPDATE chunks c SET context = d.title FROM documents d WHERE d.id = c.document_id")
    op.execute("ALTER TABLE chunks ADD COLUMN search text GENERATED ALWAYS AS (context || E'\\n' || text) STORED")
    op.execute(f"CREATE INDEX chunks_bm25_idx ON chunks USING bm25 (id, search) WITH (text_fields = '{TOKENIZER}')")
    op.execute("DROP INDEX chunks_tsv_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN tsv")


def downgrade():
    op.execute("ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED")
    op.execute("CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv)")
    op.execute("DROP INDEX chunks_bm25_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN search")
    op.execute("ALTER TABLE chunks DROP COLUMN context")

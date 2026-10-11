"""chunks.keyword_only: chunks the sync worker must not embed (review of PR #35)

Some chunks are meant to be found by keyword only: today the development seed's Company A filler
(~20,000 chunks, app/seed_scale.py), whose embedding would cost about 2 million TokenHub tokens
nobody asked for. Whoever writes a chunk sets the flag; the worker (app/sync.py embed_missing) only
looks at chunks still to embed through a partial index, so it never joins documents and never
re-reads chunks it will skip. Existing chunks default to false: nothing changes for synced content.
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE chunks ADD COLUMN keyword_only boolean NOT NULL DEFAULT false")
    op.execute("CREATE INDEX chunks_to_embed_idx ON chunks (id) WHERE embedding IS NULL AND NOT keyword_only")


def downgrade():
    op.execute("DROP INDEX IF EXISTS chunks_to_embed_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN keyword_only")

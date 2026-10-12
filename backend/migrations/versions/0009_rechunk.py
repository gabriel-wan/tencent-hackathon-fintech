"""Re-chunk and re-embed for the new chunker and embedding input (ADR-012)

Synced documents lose their content hash: the sync worker then downloads their text again and rewrites their
chunks (app/sync.py treats a document without a hash as unknown), keeping the old chunks and vectors searchable
until it does. Seeded documents are never synced again, so their vectors are cleared instead and the worker
embeds them again with their title. Nothing is lost: everything is rebuilt from the sources.
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE documents SET content_hash = NULL WHERE NOT metadata ? 'seed'")
    op.execute("UPDATE chunks c SET embedding = NULL FROM documents d "
               "WHERE d.id = c.document_id AND d.metadata ? 'seed' AND c.embedding IS NOT NULL")


def downgrade():
    pass  # the next sync rebuilds whatever this changed

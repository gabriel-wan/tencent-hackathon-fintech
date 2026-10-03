"""core schema: users, sessions, boundary, documents, chunks, sync state, audit log

Shared contract between connectors (write documents/chunks), the query
pipeline (reads them) and the API. See docs/architecture/QUERY_PIPELINE.md.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE = [
    # People. Emails are stored lower-case so linking by email (ADR-002) is exact.
    """
    CREATE TABLE users (
        id          bigserial PRIMARY KEY,
        email       text NOT NULL UNIQUE CHECK (email = lower(email)),
        name        text NOT NULL DEFAULT '',
        is_admin    boolean NOT NULL DEFAULT false,
        created_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    # Who a user is on each platform, as namespaced principals, e.g.
    # slack:user:U024, slack:members, google:user:a@co.com, google:domain:co.com.
    """
    CREATE TABLE user_principals (
        user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        principal  text   NOT NULL,
        PRIMARY KEY (user_id, principal)
    )
    """,
    # Server-side sessions. Only a SHA-256 of the cookie token is stored.
    """
    CREATE TABLE sessions (
        token_hash  text PRIMARY KEY,
        user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  timestamptz NOT NULL DEFAULT now(),
        expires_at  timestamptz NOT NULL
    )
    """,
    # Admin boundary (ADR-002): only documents inside these containers are used.
    """
    CREATE TABLE boundary (
        source      text NOT NULL,
        scope_id    text NOT NULL,
        scope_type  text NOT NULL CHECK (scope_type IN ('channel', 'folder', 'project', 'space')),
        title       text NOT NULL DEFAULT '',
        added_by    bigint REFERENCES users(id) ON DELETE SET NULL,
        added_at    timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (source, scope_id)
    )
    """,
    # One row per source item (Slack thread, Drive file, ...). The ACL lives
    # here, once per document; chunks inherit it through document_id.
    """
    CREATE TABLE documents (
        id            bigserial PRIMARY KEY,
        source        text NOT NULL CHECK (source IN ('slack', 'drive', 'jira', 'confluence')),
        source_id     text NOT NULL,
        scope_id      text NOT NULL,
        title         text NOT NULL DEFAULT '',
        url           text NOT NULL DEFAULT '',
        updated_at    timestamptz NOT NULL,
        acl           text[] NOT NULL DEFAULT '{}',
        metadata      jsonb NOT NULL DEFAULT '{}',
        content_hash  text,
        deleted_at    timestamptz,
        ingested_at   timestamptz NOT NULL DEFAULT now(),
        UNIQUE (source, source_id)
    )
    """,
    "CREATE INDEX documents_acl_idx ON documents USING gin (acl)",
    "CREATE INDEX documents_scope_idx ON documents (source, scope_id)",
    # Searchable pieces of a document. Text must be at most 2,000 characters
    # (TokenHub embedding limit). tsv is computed by Postgres.
    """
    CREATE TABLE chunks (
        id           bigserial PRIMARY KEY,
        document_id  bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        ordinal      integer NOT NULL,
        text         text NOT NULL CHECK (char_length(text) <= 2000),
        tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
        embedding    vector(1024),
        text_hash    text,
        UNIQUE (document_id, ordinal)
    )
    """,
    "CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv)",
    # Connector cursors (Task 1).
    """
    CREATE TABLE sync_state (
        source      text NOT NULL,
        key         text NOT NULL,
        cursor      text,
        updated_at  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (source, key)
    )
    """,
    # Audit trail (ADR-007). Append-only is enforced by triggers below.
    # prev_hash/hash are filled by the hash chain (roadmap, 5-6 Oct).
    """
    CREATE TABLE audit_events (
        id          bigserial PRIMARY KEY,
        ts          timestamptz NOT NULL DEFAULT now(),
        user_id     bigint,
        event_type  text NOT NULL,
        payload     jsonb NOT NULL,
        prev_hash   text,
        hash        text
    )
    """,
    "CREATE INDEX audit_events_user_ts_idx ON audit_events (user_id, ts)",
    """
    CREATE FUNCTION audit_events_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'audit_events is append-only';
    END
    $$
    """,
    """
    CREATE TRIGGER audit_events_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()
    """,
    """
    CREATE TRIGGER audit_events_no_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only()
    """,
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS audit_events",
    "DROP FUNCTION IF EXISTS audit_events_append_only()",
    "DROP TABLE IF EXISTS sync_state",
    "DROP TABLE IF EXISTS chunks",
    "DROP TABLE IF EXISTS documents",
    "DROP TABLE IF EXISTS boundary",
    "DROP TABLE IF EXISTS sessions",
    "DROP TABLE IF EXISTS user_principals",
    "DROP TABLE IF EXISTS users",
]


def upgrade():
    for statement in UPGRADE:
        op.execute(statement)


def downgrade():
    for statement in DOWNGRADE:
        op.execute(statement)

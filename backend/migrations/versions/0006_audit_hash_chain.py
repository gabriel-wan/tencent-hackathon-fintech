"""audit hash chain (ADR-007): one chain per company, and an app role that can't change the log

Every audit record gets the company it belongs to and the hash of the previous record of the same
company, so changing or deleting any record breaks the chain (app/audit/log.py verifies it). The hash
is computed by the database function audit_event_hash, so writing and verifying always hash exactly
the same text. Records of people without a company form their own chain (company_id NULL).

Existing records are given their user's company and hashed in id order, so the chain starts at this
migration: earlier records were already protected by the append-only triggers (0002).

The app now runs as the role knowbuddy_app (app/db.py), which may read and add audit records but not
update, delete or truncate them, nor alter the table to switch its triggers off. Migrations still run
as the database owner. audit_events deliberately has no foreign key to companies: the log must outlive
a deleted company, and a cascade would hit the TRUNCATE trigger.
"""
from alembic import op

from app.db import APP_ROLE

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Changing any input changes the hash. The time is written in UTC so the session time zone can't
# change the text, and jsonb's text form is canonical (sorted keys, no spacing choices).
HASH_FUNCTION = r"""
    CREATE FUNCTION audit_event_hash(prev_hash text, id bigint, ts timestamptz, company_id bigint,
                                     user_id bigint, event_type text, payload jsonb)
    RETURNS text LANGUAGE sql STABLE AS $$
        SELECT encode(sha256(convert_to(concat_ws(E'\n',
            coalesce(prev_hash, ''),
            id::text,
            to_char(ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
            coalesce(company_id::text, ''),
            coalesce(user_id::text, ''),
            event_type,
            payload::text), 'UTF8')), 'hex')
    $$
"""

# Existing records, in order: link each to the previous record of its company.
BACKFILL = """
    DO $$
    DECLARE r record; prev text;
    BEGIN
        FOR r IN SELECT * FROM audit_events ORDER BY id LOOP
            SELECT hash INTO prev FROM audit_events
            WHERE company_id IS NOT DISTINCT FROM r.company_id AND id < r.id ORDER BY id DESC LIMIT 1;
            UPDATE audit_events
            SET prev_hash = prev,
                hash = audit_event_hash(prev, r.id, r.ts, r.company_id, r.user_id, r.event_type, r.payload)
            WHERE id = r.id;
        END LOOP;
    END $$
"""

UPGRADE = [
    "ALTER TABLE audit_events ADD COLUMN company_id bigint",
    HASH_FUNCTION,
    "ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update_delete",
    "UPDATE audit_events e SET company_id = u.company_id FROM users u WHERE u.id = e.user_id",
    BACKFILL,
    "ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_update_delete",
    "ALTER TABLE audit_events ALTER COLUMN hash SET NOT NULL",
    "CREATE INDEX audit_events_company_id_idx ON audit_events (company_id, id)",
    # The app's role (roles are shared by every database on the server, hence IF NOT EXISTS).
    f"""
    DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} NOLOGIN;
        END IF;
    END $$
    """,
    f"GRANT {APP_ROLE} TO CURRENT_USER",  # lets a non-superuser owner connect as it too
    f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
    f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
    f"GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
    # The audit log: read and add only.
    f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM {APP_ROLE}",
]

DOWNGRADE = [
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {APP_ROLE}",
    f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}",
    f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}",
    f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}",
    # The role itself stays: another database on the same server may still use it.
    "DROP INDEX audit_events_company_id_idx",
    "ALTER TABLE audit_events ALTER COLUMN hash DROP NOT NULL",
    "ALTER TABLE audit_events DROP COLUMN company_id",
    "DROP FUNCTION audit_event_hash",
]


def upgrade():
    for statement in UPGRADE:
        op.execute(statement)


def downgrade():
    for statement in DOWNGRADE:
        op.execute(statement)

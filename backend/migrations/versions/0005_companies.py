"""companies: many companies share one deployment, each sees only its own data

Every document, boundary scope and sync cursor belongs to one company; a user does once a Slack or
Atlassian connection names it (until then, none: they see nothing). Search filters on
the user's company first, so principals held in every company (`public`, `slack:members`) never
reach another company's documents. Source IDs are unique only within a company (Jira and
Confluence IDs are per site).

Existing documents, boundary and cursors (e.g. a seeded local database) move into one company
named "Default"; existing users get none until their next Slack or Atlassian connection.
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TABLES = ("users", "documents", "boundary", "sync_state")
DATA = TABLES[1:]  # always belong to a company

UPGRADE = [
    # How a sign-in is matched to its company (app/companies.py).
    """
    CREATE TABLE companies (
        id                  bigserial PRIMARY KEY,
        name                text NOT NULL,
        slack_team_id       text UNIQUE,
        atlassian_cloud_id  text UNIQUE,
        created_at          timestamptz NOT NULL DEFAULT now()
    )
    """,
    # Existing data (e.g. seeded) goes into "Default". Existing users get no company: their next Slack or
    # Atlassian connection puts them in the right one (a user may have none, e.g. Google Drive only).
    "INSERT INTO companies (name) SELECT 'Default' WHERE "
    + " OR ".join(f"EXISTS (SELECT 1 FROM {t})" for t in DATA),
    *(f"ALTER TABLE {t} ADD COLUMN company_id bigint REFERENCES companies(id) ON DELETE CASCADE"
      for t in TABLES),
    *(f"UPDATE {t} SET company_id = (SELECT min(id) FROM companies)" for t in DATA),
    *(f"ALTER TABLE {t} ALTER COLUMN company_id SET NOT NULL" for t in DATA),
    "ALTER TABLE documents DROP CONSTRAINT documents_source_source_id_key",
    "ALTER TABLE documents ADD UNIQUE (company_id, source, source_id)",
    "DROP INDEX documents_scope_idx",
    "CREATE INDEX documents_scope_idx ON documents (company_id, source, scope_id)",
    "ALTER TABLE boundary DROP CONSTRAINT boundary_pkey",
    "ALTER TABLE boundary ADD PRIMARY KEY (company_id, source, scope_id)",
    "ALTER TABLE sync_state DROP CONSTRAINT sync_state_pkey",
    "ALTER TABLE sync_state ADD PRIMARY KEY (company_id, source, key)",
]

DOWNGRADE = [
    "ALTER TABLE sync_state DROP CONSTRAINT sync_state_pkey",
    "ALTER TABLE sync_state ADD PRIMARY KEY (source, key)",
    "ALTER TABLE boundary DROP CONSTRAINT boundary_pkey",
    "ALTER TABLE boundary ADD PRIMARY KEY (source, scope_id)",
    "DROP INDEX documents_scope_idx",
    "CREATE INDEX documents_scope_idx ON documents (source, scope_id)",
    "ALTER TABLE documents DROP CONSTRAINT documents_company_id_source_source_id_key",
    "ALTER TABLE documents ADD CONSTRAINT documents_source_source_id_key UNIQUE (source, source_id)",
    *(f"ALTER TABLE {t} DROP COLUMN company_id" for t in TABLES),
    "DROP TABLE companies",
]


def upgrade():
    for statement in UPGRADE:
        op.execute(statement)


def downgrade():
    for statement in DOWNGRADE:
        op.execute(statement)

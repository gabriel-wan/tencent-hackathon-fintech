"""the app logs in as knowbuddy_app itself (ADR-007; review of PR #11)

0006 had the app log in as the database owner and switch to knowbuddy_app on connect. One statement
(`SET ROLE NONE`) switched it back to the owner, a superuser in Docker, who can turn the audit
triggers off. Now knowbuddy_app is a login of its own, so the app's sessions have nothing more
powerful to return to. Its password comes from APP_DB_PASSWORD and is set by migrations/env.py on
every migration run, so changing it in .env takes effect on the next `docker compose up`.

Also drops rights the app never uses: TRUNCATE on every table (only the tests emptied tables, and
they now do it as the owner), and the owner's membership of knowbuddy_app, which only the old
switch on connect needed.
"""
from alembic import op

from app.db import APP_ROLE

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UPGRADE = [
    f"ALTER ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT",
    f"REVOKE TRUNCATE ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE TRUNCATE ON TABLES FROM {APP_ROLE}",
    f"REVOKE {APP_ROLE} FROM CURRENT_USER",
]

DOWNGRADE = [
    f"GRANT {APP_ROLE} TO CURRENT_USER",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT TRUNCATE ON TABLES TO {APP_ROLE}",
    f"GRANT TRUNCATE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
    f"REVOKE TRUNCATE ON audit_events FROM {APP_ROLE}",
    f"ALTER ROLE {APP_ROLE} NOLOGIN",
]


def upgrade():
    for statement in UPGRADE:
        op.execute(statement)


def downgrade():
    for statement in DOWNGRADE:
        op.execute(statement)

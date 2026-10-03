from alembic import context

import app.connectors.store  # noqa: F401  registers its tables (and app.auth's) on metadata
from app.db import engine, metadata

# Migrations are hand-written; target_metadata lets `alembic check` catch drift from the code.
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()

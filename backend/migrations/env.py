from alembic import context

from app.db import owner_engine  # the owner: the app's own role can't create tables or roles

with owner_engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()

from alembic import context
from psycopg import sql

from app.db import APP_ROLE, app_db_password, owner_engine  # the owner: the app's role can't create tables or roles

with owner_engine().connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
        # Every run (the `migrate` service runs before the backend starts): give the app's login the
        # password from .env, so changing it there takes effect on the next start. Skipped until 0006
        # has created the role. Nothing is logged: the statement holds the password.
        if connection.exec_driver_sql(f"SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}'").first():
            raw = connection.connection.driver_connection
            connection.exec_driver_sql(
                sql.SQL("ALTER ROLE {} WITH PASSWORD {}")
                .format(sql.Identifier(APP_ROLE), sql.Literal(app_db_password()))
                .as_string(raw)
            )

import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy import URL, Engine, MetaData, create_engine

# Every table registers here, defined in the module that owns it (app/auth.py, app/connectors/store.py).
# migrations/env.py compares it with the database: `alembic check`.
metadata = MetaData()

engine = create_engine(
    URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        database=os.environ["POSTGRES_DB"],
    ),
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3},
)


def get_engine():
    """FastAPI dependency (overridden in tests). Handlers open short transactions themselves."""
    return engine


Db = Annotated[Engine, Depends(get_engine)]  # in endpoints: def handler(engine: Db)

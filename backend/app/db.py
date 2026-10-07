import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Annotated

from fastapi import Depends
from sqlalchemy import URL, Connection, Engine, create_engine

# Created by migration 0006: may read and add audit records, never change or remove them (ADR-007).
APP_ROLE = "knowbuddy_app"

_url = URL.create(
    "postgresql+psycopg",
    username=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ["POSTGRES_HOST"],
    database=os.environ["POSTGRES_DB"],
)

# Migrations only (migrations/env.py): the database owner, who creates tables and roles.
owner_engine = create_engine(_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})

# Everything else: every session starts as APP_ROLE, so a bug or an injected statement can't alter the
# audit log. ASSUMPTION: the login is still the owner; a production server should give the app its own
# login that is only a member of APP_ROLE (docs/SECURITY.md, INV-7).
engine = create_engine(
    _url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3, "options": f"-c role={APP_ROLE}"},
)


def get_engine():
    """FastAPI dependency (overridden in tests). Handlers open short transactions themselves."""
    return engine


Db = Annotated[Engine, Depends(get_engine)]  # in endpoints: def handler(engine: Db)

# Opens one short transaction per use (`with tx() as conn:`), e.g. engine.begin.
Tx = Callable[[], AbstractContextManager[Connection]]

import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from functools import cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import URL, Connection, Engine, create_engine

# The app's own database login (migrations 0006, 0007): it may read and add audit records, never
# change or remove them, nor alter tables (ADR-007).
APP_ROLE = "knowbuddy_app"


def app_db_password() -> str:
    password = os.environ.get("APP_DB_PASSWORD", "")
    if not password:
        raise RuntimeError("APP_DB_PASSWORD is not set: add it to backend/.env (see backend/.env.example). "
                           "It is the app's own database password, set on the database by the migrate service.")
    return password


def _url(username: str, password: str) -> URL:
    return URL.create("postgresql+psycopg", username=username, password=password,
                      host=os.environ["POSTGRES_HOST"], database=os.environ["POSTGRES_DB"])


@cache
def owner_engine() -> Engine:
    """The database owner, who creates tables and roles: migrations (migrations/env.py) and tests only.
    Built on first use, so the app itself never needs the owner's password."""
    return create_engine(_url(os.environ["POSTGRES_USER"], os.environ["POSTGRES_PASSWORD"]),
                         pool_pre_ping=True, connect_args={"connect_timeout": 3})

# Everything else logs in as APP_ROLE itself, so no statement can switch to a more powerful role:
# `SET ROLE NONE` stays APP_ROLE. The owner's password is never used by the app's sessions.
engine = create_engine(_url(APP_ROLE, app_db_password()), pool_pre_ping=True, connect_args={"connect_timeout": 3})


def get_engine():
    """FastAPI dependency (overridden in tests). Handlers open short transactions themselves."""
    return engine


Db = Annotated[Engine, Depends(get_engine)]  # in endpoints: def handler(engine: Db)

# Opens one short transaction per use (`with tx() as conn:`), e.g. engine.begin.
Tx = Callable[[], AbstractContextManager[Connection]]

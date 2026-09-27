import os

from sqlalchemy import URL, create_engine

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

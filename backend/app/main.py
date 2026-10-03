from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth import router as auth_router
from app.connectors.api import router as connectors_router
from app.db import engine

app = FastAPI(title="Internal Brain API")
app.include_router(auth_router)
app.include_router(connectors_router)


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
    except SQLAlchemyError:
        return JSONResponse({"db": "down", "pgvector": None}, status_code=503)
    return {"db": "ok", "pgvector": version}

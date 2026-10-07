import logging
import os
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import dev_router, router
from app.audit.api import router as audit_router
from app.connectors.admin import router as admin_router
from app.connectors.api import dev_router as connectors_dev_router
from app.connectors.api import router as connectors_router
from app.db import engine

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "info").upper())


def create_app(app_env: str | None = None) -> FastAPI:
    # Anything other than an explicit "development" is treated as production.
    app_env = app_env if app_env is not None else os.environ.get("APP_ENV", "production")
    app_url = os.environ.get("APP_URL", "")
    if app_env == "development" and app_url and urlparse(app_url).hostname not in ("localhost", "127.0.0.1"):
        # Dev routes let anyone sign in as anyone: only ever on this machine, never a server (http or https).
        raise RuntimeError(f"APP_ENV=development needs a localhost APP_URL, not {app_url}: set APP_ENV=production")
    app = FastAPI(title="Internal Brain API")
    app.state.app_env = app_env

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

    app.include_router(router)
    app.include_router(connectors_router)
    app.include_router(admin_router)
    app.include_router(audit_router)
    if app_env == "development":
        app.include_router(dev_router)
        app.include_router(connectors_dev_router)
    return app


app = create_app()

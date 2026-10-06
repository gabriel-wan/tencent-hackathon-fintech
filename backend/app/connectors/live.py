"""Live permission check (ADR-003) for app/auth/live_check.py: each source answers for the asking user,
through that user's own connection, right now. A revoked share or channel removal applies on the
next question, not the next sync. Any error (e.g. not connected) raises, and live_check denies.
"""

from fastapi import Depends, Request

from app.api.deps import current_user
from app.auth.live_check import default_checkers
from app.auth.session import User
from app.connectors import store
from app.db import engine

MODE = "live: each source, as the user"  # recorded in the audit log


def can_read(user_id: int, source: str, ids: list[str]) -> dict[str, bool]:
    allowed = store.SOURCES[source].can_read(store.client(engine, user_id, source), ids)
    return {i: i in allowed for i in ids}


def for_request(request: Request, user: User = Depends(current_user)):
    """FastAPI dependency: the `checkers_factory` for app.pipeline.query.answer_question, asking as this
    user. Only in development, a persona with no connection at all (the seed's fictional users, whose
    documents no real source knows) keeps the stored-ACL stub."""
    if request.app.state.app_env == "development":
        with engine.connect() as db:
            if not store.list_connections(db, user.id):
                return default_checkers

    def checkers(_candidates, _principals):
        return {s: lambda _principal, ids, s=s: can_read(user.id, s, ids) for s in store.SOURCES}

    checkers.mode = MODE
    return checkers

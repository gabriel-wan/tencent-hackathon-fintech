"""Company admin API (ADR-002): choose the boundary, and sync now (ADR-005). Admins only, and only
ever their own company.

GET    /api/admin/scopes/{source}                channels / folders / projects / spaces you can see
GET    /api/admin/boundary                       your company's boundary, with each scope's last_synced_at
PUT    /api/admin/boundary/{source}/{scope_id}   add a scope (body: {"title": "..."})
DELETE /api/admin/boundary/{source}/{scope_id}   remove a scope; its documents are soft-deleted
POST   /api/admin/sync                           sync your company now, in the background (202)

Boundary changes and sync requests are recorded in the audit log.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app import sync
from app.api.deps import current_user
from app.audit.log import record_event
from app.auth.session import User
from app.connectors import store
from app.connectors.api import PROVIDER_ERRORS, provider_error
from app.db import Db

router = APIRouter(prefix="/api/admin", tags=["admin"])

SCOPE_TYPE = {"slack": "channel", "drive": "folder", "jira": "project", "confluence": "space"}
# Channel, folder and space IDs and project keys are all plain IDs. They end up inside JQL and Drive
# queries, so nothing else is accepted.
ScopeId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    return user


def _source(source: str) -> str:
    if source not in store.SOURCES:
        raise HTTPException(404, f"unknown source: {source}")
    return source


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=200)


@router.get("/scopes/{source}")
def scopes(source: str, engine: Db, admin: User = Depends(require_admin)):
    try:
        return store.SOURCES[_source(source)].scopes(store.client(engine, admin.id, source))
    except store.NotConnected as e:
        raise HTTPException(404, f"connect {source} first") from e
    except store.ReconnectNeeded as e:
        raise HTTPException(401, f"{source} access expired: connect again") from e
    except PROVIDER_ERRORS as e:  # e.g. a revoked Slack token: "connect again", not a 500
        raise provider_error(source, e) from e


@router.get("/boundary")
def boundary(engine: Db, admin: User = Depends(require_admin)):
    with engine.connect() as db:
        rows = db.execute(text("SELECT b.source, b.scope_id, b.scope_type, b.title, b.added_at, "
                               "s.updated_at AS last_synced_at FROM boundary b LEFT JOIN sync_state s "
                               "ON s.company_id = b.company_id AND s.source = b.source AND s.key = b.scope_id "
                               "WHERE b.company_id = :c ORDER BY b.source, b.title"), {"c": admin.company_id})
        return [dict(r) for r in rows.mappings()]


@router.put("/boundary/{source}/{scope_id}", status_code=204)
def add_scope(source: str, scope_id: ScopeId, body: Scope, engine: Db, admin: User = Depends(require_admin)):
    with engine.begin() as db:
        db.execute(text("INSERT INTO boundary (company_id, source, scope_id, scope_type, title, added_by) "
                        "VALUES (:c, :s, :i, :t, :ti, :u) "
                        "ON CONFLICT (company_id, source, scope_id) DO UPDATE SET title = EXCLUDED.title"),
                   {"c": admin.company_id, "s": _source(source), "i": scope_id, "t": SCOPE_TYPE[source],
                    "ti": body.title, "u": admin.id})
        record_event(db, admin.id, "boundary_added", {"source": source, "scope_id": scope_id, "title": body.title})
    return Response(status_code=204)


@router.delete("/boundary/{source}/{scope_id}", status_code=204)
def remove_scope(source: str, scope_id: str, engine: Db, admin: User = Depends(require_admin)):
    key = {"c": admin.company_id, "s": _source(source), "i": scope_id}
    with engine.begin() as db:
        db.execute(text("DELETE FROM boundary WHERE company_id = :c AND source = :s AND scope_id = :i"), key)
        db.execute(text("DELETE FROM sync_state WHERE company_id = :c AND source = :s AND key = :i"), key)
        db.execute(text("UPDATE documents SET deleted_at = now() WHERE company_id = :c AND source = :s "
                        "AND scope_id = :i AND deleted_at IS NULL"), key)
        record_event(db, admin.id, "boundary_removed", {"source": source, "scope_id": scope_id})
    return Response(status_code=204)


@router.post("/sync", status_code=202)
def sync_now(tasks: BackgroundTasks, engine: Db, admin: User = Depends(require_admin)):
    with engine.begin() as db:
        record_event(db, admin.id, "sync_requested", {"company_id": admin.company_id})
    tasks.add_task(sync.sync_company, engine, admin.company_id)
    return {"syncing": True}

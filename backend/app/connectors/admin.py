"""Company admin API (ADR-002): choose the boundary, and sync now (ADR-005). Admins only, and only
ever their own company.

GET    /api/admin/scopes/{source}                channels / folders / projects / spaces you can see
GET    /api/admin/boundary                       your company's boundary, with each scope's last_synced_at
PUT    /api/admin/boundary/{source}/{scope_id}   add a scope (body: {"title": "..."})
DELETE /api/admin/boundary/{source}/{scope_id}   remove a scope; its documents are soft-deleted
POST   /api/admin/boundary/{source}/bulk         add and remove up to 50 scopes in one go (one transaction)
POST   /api/admin/sync                           sync your company now, in the background (202)

Boundary changes (one event per scope, also in bulk) and sync requests are recorded in the audit log.
A Drive folder can't be added when a folder above or below it is already in: sync includes subfolders, and
two overlapping scopes would fight over the same files (409, naming the other folder).
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app import sync
from app.api.deps import current_user
from app.audit.log import record_event
from app.auth.session import User
from app.connectors import drive, store
from app.connectors.api import PROVIDER_ERRORS, provider_error
from app.db import Db

router = APIRouter(prefix="/api/admin", tags=["admin"])

SCOPE_TYPE = {"slack": "channel", "drive": "folder", "jira": "project", "confluence": "space"}
# Channel, folder and space IDs and project keys are all plain IDs. They end up inside JQL and Drive
# queries, so nothing else is accepted.
SCOPE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,128}$"
ScopeId = Annotated[str, Path(pattern=SCOPE_ID_PATTERN)]
BULK_LIMIT = 50  # scopes per bulk request: the page asks the admin to narrow the list beyond this


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


def _insert(db, admin: User, source: str, scope_id: str, title: str) -> bool:
    """Adds a scope (or refreshes its title). Audited only when it is new: re-adding one already in the boundary
    (a stale page, two admins at once) changes nothing, so it must not appear in the trail (review of the UI
    revamp PR). Callers hold the boundary lock, so the check and the write see the same boundary."""
    key = {"c": admin.company_id, "s": source, "i": scope_id}
    new = db.execute(text("SELECT 1 FROM boundary WHERE company_id = :c AND source = :s AND scope_id = :i"),
                     key).first() is None
    db.execute(text("INSERT INTO boundary (company_id, source, scope_id, scope_type, title, added_by) "
                    "VALUES (:c, :s, :i, :t, :ti, :u) "
                    "ON CONFLICT (company_id, source, scope_id) DO UPDATE SET title = EXCLUDED.title"),
               {**key, "t": SCOPE_TYPE[source], "ti": title, "u": admin.id})
    if new:
        record_event(db, admin.id, "boundary_added", {"source": source, "scope_id": scope_id, "title": title})
    return new


def _delete(db, admin: User, source: str, scope_id: str) -> bool:
    """Removes a scope. Audited only when it was in the boundary: a second removal (two admins at once, a stale
    page) changes nothing, so it must not appear in the trail as if it had (review of the UI revamp PR)."""
    key = {"c": admin.company_id, "s": source, "i": scope_id}
    removed = db.execute(text("DELETE FROM boundary WHERE company_id = :c AND source = :s AND scope_id = :i"),
                         key).rowcount
    db.execute(text("DELETE FROM sync_state WHERE company_id = :c AND source = :s AND key = :i"), key)
    db.execute(text("UPDATE documents SET deleted_at = now() WHERE company_id = :c AND source = :s "
                    "AND scope_id = :i AND deleted_at IS NULL"), key)
    if removed:
        record_event(db, admin.id, "boundary_removed", {"source": source, "scope_id": scope_id})
    return bool(removed)


BOUNDARY_LOCK = 4747  # first key of the per-company advisory lock on boundary changes (the second is the company)


def _lock(db, admin: User) -> None:
    """One boundary change per company at a time, until its transaction ends: the overlap check and the write
    see the same boundary, so two adds (a folder and its parent) can't both pass."""
    # Postgres lock keys are 32-bit: fold the id in, as the audit chain's lock does, so huge ids don't fail (a
    # shared key only means two companies' changes wait for each other).
    db.execute(text("SELECT pg_advisory_xact_lock(:k, CAST(:c AS integer))"),
               {"k": BOUNDARY_LOCK, "c": admin.company_id % 2147483647})


def _drive_overlaps(db, engine, admin: User, adding: dict[str, str], removing: set[str] = frozenset()) -> None:
    """Refuses (409) Drive folders that sit above or below another folder in the boundary, or in the same
    request. `adding`: folder ID -> its title. Reads the boundary in the caller's locked transaction, and asks
    Drive, as the admin, for the ancestors of each folder involved, sharing one parent cache across them."""
    titles = dict(db.execute(text("SELECT scope_id, title FROM boundary WHERE company_id = :c "
                                  "AND source = 'drive'"), {"c": admin.company_id}).all())
    others = {i: t for i, t in titles.items() if i not in removing}
    if not others and len(adding) < 2:
        return
    try:
        client = store.client(engine, admin.id, "drive")
        parent_of: dict[str, str | None] = {}
        chains = {i: drive.ancestors(client, i, parent_of) for i in {*others, *adding}}
    except store.NotConnected as e:
        raise HTTPException(404, "connect drive first") from e
    except store.ReconnectNeeded as e:
        raise HTTPException(401, "drive access expired: connect again") from e
    except PROVIDER_ERRORS as e:
        raise provider_error("drive", e) from e
    taken = dict(others)
    for folder, name in adding.items():
        name = name or folder
        taken.pop(folder, None)  # re-adding the same folder is fine
        for other, title in taken.items():
            if other in chains[folder]:
                raise HTTPException(409, f"{name} is inside {title or other}, which is already in the boundary")
            if folder in chains[other]:
                raise HTTPException(409, f"{name} contains {title or other}, which is already in the boundary: "
                                         "remove that first")
        taken[folder] = name


@router.put("/boundary/{source}/{scope_id}", status_code=204)
def add_scope(source: str, scope_id: ScopeId, body: Scope, engine: Db, admin: User = Depends(require_admin)):
    with engine.begin() as db:
        _lock(db, admin)
        if _source(source) == "drive":
            _drive_overlaps(db, engine, admin, {scope_id: body.title})
        _insert(db, admin, source, scope_id, body.title)
    return Response(status_code=204)


@router.delete("/boundary/{source}/{scope_id}", status_code=204)
def remove_scope(source: str, scope_id: str, engine: Db, admin: User = Depends(require_admin)):
    with engine.begin() as db:
        _lock(db, admin)
        _delete(db, admin, _source(source), scope_id)
    return Response(status_code=204)


class BulkScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_id: str = Field(pattern=SCOPE_ID_PATTERN)
    title: str = Field(default="", max_length=200)


class Bulk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    add: list[BulkScope] = Field(default_factory=list, max_length=BULK_LIMIT)
    remove: list[Annotated[str, Field(pattern=SCOPE_ID_PATTERN)]] = Field(default_factory=list, max_length=BULK_LIMIT)


@router.post("/boundary/{source}/bulk")
def bulk(source: str, body: Bulk, engine: Db, admin: User = Depends(require_admin)):
    """Several scopes of one tool at once, all or nothing, each change its own audit event (as one at a time)."""
    source = _source(source)
    adding = {s.scope_id: s.title for s in body.add}  # duplicates collapse
    removing = set(body.remove)
    if not adding and not removing:
        raise HTTPException(422, "nothing to add or remove")
    if len(adding) + len(removing) > BULK_LIMIT:
        raise HTTPException(422, f"at most {BULK_LIMIT} scopes at once")
    if removing & set(adding):
        raise HTTPException(422, "a scope can't be added and removed at once")
    with engine.begin() as db:  # one transaction: a failure changes nothing
        _lock(db, admin)
        if source == "drive" and adding:
            _drive_overlaps(db, engine, admin, adding, removing)
        removed = sum(_delete(db, admin, source, scope_id) for scope_id in sorted(removing))
        added = sum(_insert(db, admin, source, scope_id, title) for scope_id, title in adding.items())
    return {"added": added, "removed": removed}  # only scopes that actually changed


@router.post("/sync", status_code=202)
def sync_now(tasks: BackgroundTasks, engine: Db, admin: User = Depends(require_admin)):
    with engine.begin() as db:
        record_event(db, admin.id, "sync_requested", {"company_id": admin.company_id})
    tasks.add_task(sync.sync_company, engine, admin.company_id)
    return {"syncing": True}

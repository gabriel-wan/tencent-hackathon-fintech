"""Audit API (ADR-007): the company admin (also its compliance officer) searches and verifies the
audit trail. Admins only, and only ever their own company's records. Every search and every
verification is itself recorded in the trail.

GET  /api/admin/audit          search, newest first (filters below); next page: ?before_id=<next_before_id>
POST /api/admin/audit/verify   recompute the company's hash chain; reports the first broken record

Example, the challenge's audit inquiry ("everything jdoe accessed in the payment-gateway space in the
last 30 days"):  GET /api/admin/audit?user=jdoe@co.com&source=confluence&scope_id=<space id>&since=<date>
"""
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_tx
from app.audit.log import SEARCH_LIMIT, record_event, search_events, verify_chain
from app.auth.session import User
from app.connectors.admin import SCOPE_ID_PATTERN, require_admin
from app.db import Tx

router = APIRouter(prefix="/api/admin/audit", tags=["audit"])

Source = Literal["slack", "drive", "jira", "confluence"]


@router.get("")
def search(
    admin: User = Depends(require_admin),
    tx: Tx = Depends(get_tx),
    user: Annotated[str | None, Query(max_length=320, description="the user's email")] = None,
    event_type: Annotated[str | None, Query(pattern=r"^[a-z_]{1,40}$")] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    document: Annotated[str | None, Query(max_length=300, description='a document key, e.g. "jira:10042"')] = None,
    source: Source | None = None,
    scope_id: Annotated[str | None, Query(pattern=SCOPE_ID_PATTERN)] = None,
    before_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=SEARCH_LIMIT)] = 50,
):
    if scope_id is not None and source is None:  # a scope id means nothing without its tool
        raise HTTPException(422, "scope_id needs source (slack, drive, jira or confluence)")
    filters = {"user": user, "event_type": event_type, "since": since, "until": until, "document": document,
               "source": source, "scope_id": scope_id, "before_id": before_id, "limit": limit}
    with tx() as conn:
        records = search_events(
            conn, admin.company_id, user_email=user, event_type=event_type, since=since, until=until,
            document=document, source=source, scope_id=scope_id, before_id=before_id,
            limit=limit,
        )
        # Searching the trail is itself audited (ADR-007): who looked at what, and how much they saw.
        record_event(conn, admin.id, "audit_searched",
                     {"filters": {k: v for k, v in filters.items() if v is not None}, "results": len(records)})
    return {"records": records, "next_before_id": records[-1]["id"] if len(records) == limit else None}


@router.post("/verify")
def verify(admin: User = Depends(require_admin), tx: Tx = Depends(get_tx)):
    with tx() as conn:
        result = verify_chain(conn, admin.company_id)
        record_event(conn, admin.id, "audit_verified",
                     {k: result[k] for k in ("ok", "checked", "first_broken_id")})
    return result

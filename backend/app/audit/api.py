"""Audit API (ADR-007): the company admin (also its compliance officer) searches and verifies the
audit trail. Admins only, and only ever their own company's records. Every search and every
verification is itself recorded in the trail.

GET  /api/admin/audit          search, newest first (filters below); next page: ?before_id=<next_before_id>
POST /api/admin/audit/verify   recompute the company's hash chain; reports the first broken record
POST /api/admin/audit/ask      ask the trail in plain language (ADR-013, app/audit/assistant.py)

Example, the challenge's audit inquiry ("everything jdoe accessed in the payment-gateway space in the
last 30 days"):  GET /api/admin/audit?user=jdoe@co.com&source=confluence&scope_id=<space id>&since=<date>
"""
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import get_llm, get_tx
from app.audit.assistant import ask as ask_assistant
from app.audit.log import SEARCH_LIMIT, record_event, search_events, verify_chain
from app.auth.session import User
from app.connectors.admin import SCOPE_ID_PATTERN, require_admin
from app.db import Tx

router = APIRouter(prefix="/api/admin/audit", tags=["audit"])

Source = Literal["slack", "drive", "jira", "confluence"]

MAX_ASK_CHARS = 2000  # as the knowledge chat's questions
_ZONES = available_timezones() | {"UTC"}


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # e.g. a "company_id" field is rejected, not ignored
    question: str = Field(max_length=MAX_ASK_CHARS)
    # The officer's IANA time zone (the browser's), so "last week" and "14 Oct" mean their days, as in the table.
    time_zone: str = Field(default="UTC", max_length=64)

    @field_validator("time_zone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        if value not in _ZONES:
            raise ValueError("unknown time zone")
        return value

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value


class ChoiceOut(BaseModel):
    kind: Literal["user", "scope", "document"]
    value: str  # an email, a scope id or a document key
    label: str
    source: str | None  # a scope's tool


class DocumentFact(BaseModel):
    document: str  # a document key, e.g. "jira:10042"
    allowed: int
    denied: int
    sent: int
    cited: int
    restricted: int


class Facts(BaseModel):
    """Counted by code over every matching record (never by the model)."""
    matches: int
    more_than_shown: bool  # the search stopped at its limit: there are more matches than counted
    summarised: int  # how many of the newest matches the summary was written from
    newest: datetime | None
    oldest: datetime | None
    by_event_type: dict[str, int]
    by_user: dict[str, int]
    documents: list[DocumentFact]  # the 20 documents in the most decisions
    documents_total: int


class RecordCitation(BaseModel):
    label: str  # the [S<n>] marker in `answer`
    record_id: int


class AskResponse(BaseModel):
    status: Literal["answered", "clarify", "no_records", "unavailable"]
    answer: str  # the summary, or the clarifying question
    filters: dict[str, str]  # the search, as GET /api/admin/audit query parameters
    choices: list[ChoiceOut]  # with "clarify": what an ambiguous name could mean
    facts: Facts | None
    citations: list[RecordCitation]
    audit_id: int  # this question's own audit_asked record


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


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, admin: User = Depends(require_admin), tx: Tx = Depends(get_tx), llm=Depends(get_llm)):
    result = ask_assistant(tx, admin, body.question, llm, zone=body.time_zone)
    return AskResponse(
        status=result.status,
        answer=result.answer,
        filters=result.filters,
        choices=[ChoiceOut(**vars(c)) for c in result.choices],
        facts=Facts(**result.facts) if result.facts is not None else None,
        citations=[RecordCitation(label=label, record_id=record_id) for label, record_id in result.citations],
        audit_id=result.audit_id,
    )

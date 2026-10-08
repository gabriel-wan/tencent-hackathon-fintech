"""HTTP API. Contract: docs/architecture/QUERY_PIPELINE.md."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection, text

from app.api.deps import current_user, get_conn, get_llm, get_tx
from app.auth.session import COOKIE_NAME, SESSION_HOURS, User, create_session, delete_session, get_user
from app.connectors import live
from app.db import Tx
from app.llm.client import LLMClient
from app.pipeline.query import answer_question

MAX_QUESTION_CHARS = 2000  # also the embedding input limit

router = APIRouter(prefix="/api")


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # e.g. a "user_id" field is rejected, not ignored
    question: str = Field(max_length=MAX_QUESTION_CHARS)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value


class CitationOut(BaseModel):
    id: str
    title: str
    url: str
    source: str
    updated_at: datetime
    synced_at: datetime | None
    redacted: dict[str, int]  # identifiers masked in this source for you, by kind (ADR-010)


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    audit_id: int


class MeResponse(BaseModel):
    email: str
    name: str
    is_admin: bool


@router.post("/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    user: User = Depends(current_user),
    tx: Tx = Depends(get_tx),
    llm: LLMClient = Depends(get_llm),
    checkers=Depends(live.for_request),
) -> QueryResponse:
    result = answer_question(tx, user, body.question, llm, checkers_factory=checkers)
    return QueryResponse(
        answer=result.answer,
        citations=[CitationOut(**vars(c)) for c in result.citations],
        audit_id=result.audit_id,
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(current_user)) -> MeResponse:
    return MeResponse(email=user.email, name=user.name, is_admin=user.is_admin)


@router.delete("/session", status_code=204)
def sign_out(request: Request, response: Response, conn: Connection = Depends(get_conn)) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(conn, token)
    response.delete_cookie(COOKIE_NAME)


# --- DEVELOPMENT ONLY -----------------------------------------------------------
# Stand-in for connector sign-in (ADR-002) until the Slack/Google sign-in exists:
# the persona switcher signs in as a seeded user. Registered only when
# APP_ENV=development (see app/main.py); in any other environment these routes
# do not exist.

dev_router = APIRouter(prefix="/api/dev", tags=["development only"])


class DevUser(BaseModel):
    id: int
    email: str
    name: str
    is_admin: bool


class DevSessionRequest(BaseModel):
    user_id: int


@dev_router.get("/users", response_model=list[DevUser])
def dev_users(conn: Connection = Depends(get_conn)) -> list[DevUser]:
    rows = conn.execute(text("SELECT id, email, name, is_admin FROM users ORDER BY id")).all()
    return [DevUser(**r._asdict()) for r in rows]


@dev_router.post("/session", response_model=MeResponse)
def dev_sign_in(
    body: DevSessionRequest, request: Request, response: Response, conn: Connection = Depends(get_conn)
) -> MeResponse:
    user = get_user(conn, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="No such user")
    token = create_session(conn, user.id)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=request.app.state.app_env != "development",
    )
    return MeResponse(email=user.email, name=user.name, is_admin=user.is_admin)

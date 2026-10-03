"""FastAPI dependencies: one DB transaction per request, the signed-in user, the LLM."""
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Connection

from app.auth.session import COOKIE_NAME, User, user_for_token
from app.db import engine
from app.llm.client import LLMClient, LLMNotConfigured


def get_conn() -> Iterator[Connection]:
    with engine.begin() as conn:  # commits on success, rolls back on error
        yield conn


def current_user(request: Request, conn: Connection = Depends(get_conn)) -> User:
    """The user comes only from the session cookie, never from the request body."""
    token = request.cookies.get(COOKIE_NAME)
    user = user_for_token(conn, token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


def get_llm() -> LLMClient:
    try:
        return LLMClient.from_env()
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail="LLM is not configured") from exc

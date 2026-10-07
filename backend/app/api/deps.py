"""FastAPI dependencies: one DB transaction per request, the signed-in user, the LLM."""
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Connection

from app.auth.session import COOKIE_NAME, User, user_for_token
from app.db import Tx, engine
from app.llm.client import LLMClient, LLMNotConfigured


def get_conn() -> Iterator[Connection]:
    with engine.begin() as conn:  # commits on success, rolls back on error
        yield conn


def get_tx() -> Tx:
    """For handlers that call slow external services: open short transactions, never hold one across a call."""
    return engine.begin


def current_user(request: Request, tx: Tx = Depends(get_tx)) -> User:
    """The user comes only from the session cookie, never from the request body."""
    token = request.cookies.get(COOKIE_NAME)
    user = None
    if token:
        with tx() as conn:
            user = user_for_token(conn, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


def get_llm() -> LLMClient:
    try:
        return LLMClient.from_env()
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail="LLM is not configured") from exc

"""Connectors API (ADR-002): connect, list, call and disconnect each user's own accounts.

GET    /connectors                   the 4 connectors and whether you are connected
GET    /connectors/{id}/connect      redirects to the provider's sign-in page
GET    /oauth/{provider}/callback    provider redirects back here; stores the connection
GET    /connectors/{id}/ping         calls the API as you (proves the connection works)
DELETE /connectors/{id}              disconnects (Jira and Confluence share one Atlassian sign-in)
POST   /api/dev/connectors/slack     development only: connect Slack with a pasted user token

Signing in to the first connector creates the user (if new) and signs you in to the app: the same
session as the rest of the API (app/auth/session.py, app/api/deps.py). Connector data is written
in short transactions inside each handler, never across a call to a provider.
"""

import logging
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from googleapiclient.errors import HttpError
from pydantic import BaseModel, ConfigDict, Field
from slack_sdk.errors import SlackApiError

from app import companies
from app.api.deps import current_user
from app.audit.log import record_event
from app.auth import session
from app.auth.session import User
from app.connectors import atlassian, oauth, store
from app.db import Db

log = logging.getLogger(__name__)
router = APIRouter()
dev_router = APIRouter(prefix="/api/dev", tags=["development only"])  # registered only when APP_ENV=development

CONNECTORS = {  # connector id -> (OAuth provider, display name)
    "drive": ("google", "Google Drive"),
    "slack": ("slack", "Slack"),
    "jira": ("atlassian", "Jira"),
    "confluence": ("atlassian", "Confluence"),
}
STATE_COOKIE = "oauth_state"


def _secure() -> bool:
    return oauth.app_url().startswith("https://")  # cookies are Secure only over https


def _maybe_user(request: Request, engine: Db) -> User | None:
    token = request.cookies.get(session.COOKIE_NAME)
    if not token:
        return None
    with engine.connect() as db:
        return session.user_for_token(db, token)


def _link(request: Request, engine, provider: str, account: oauth.Account, tokens: oauth.Tokens):
    """Store the connection for the person this account belongs to, creating the user if new.

    Returns (user id, new session token or None), or None if the account belongs to someone else.
    """
    with engine.begin() as db:  # committed before the response is sent
        token = request.cookies.get(session.COOKIE_NAME)
        signed_in = session.user_for_token(db, token) if token else None
        known = session.get_user_by_email(db, account.email)
        user = known.id if known else None
        owner = store.connection_owner(db, provider, account.id)
        # ADR-002: one person = one company email, and each external account belongs to one person.
        # A sign-in naming a company never moves someone out of theirs.
        has_company = known is not None and known.company_id is not None
        if (signed_in and signed_in.id != user) or (owner and owner != user) \
                or (has_company and account.company_id not in (None, known.company_id)):
            return None
        if user is None:
            user = session.create_user(db, account.email, account.name, None).id
        joins = account.company_id is not None and not has_company  # the first connection naming a company
        made_admin = joins and companies.join(db, user, account.company_id)
        company = account.company_id if joins else known and known.company_id  # the user's company now
        store.save_connection(db, user, provider, account, tokens)
        new_session = None if signed_in else session.create_session(db, user)
        record_event(db, user, "connector_connected", {"provider": provider, "account_id": account.id,
                                                       "company_id": company, "made_admin": made_admin})
    return user, new_session


def _set_session(resp: Response, token: str | None) -> None:
    if token:
        resp.set_cookie(session.COOKIE_NAME, token, max_age=session.SESSION_HOURS * 3600,
                        httponly=True, samesite="lax", secure=_secure())


def _provider(connector: str) -> str:
    if connector not in CONNECTORS:
        raise HTTPException(404, f"unknown connector: {connector}")
    return CONNECTORS[connector][0]


@router.get("/connectors")
def list_connectors(engine: Db, user: User | None = Depends(_maybe_user)):
    with engine.connect() as db:
        connected = store.list_connections(db, user.id) if user else {}
    result = []
    for connector, (provider, name) in CONNECTORS.items():
        conn = connected.get(provider)
        if conn and provider == "atlassian" and not store.atlassian_site(conn["extra"], connector):
            conn = None  # signed in to Atlassian, but the site has no access to this product
        account = {"name": conn["account_name"], "email": conn["account_email"]} if conn else None
        result.append({"id": connector, "name": name, "connected": conn is not None, "account": account})
    return result


@router.get("/connectors/{connector}/connect")
def connect(connector: str, request: Request):
    provider = _provider(connector)
    state = secrets.token_urlsafe(32)
    try:
        store.cipher()  # fail now, not after the user has signed in
        url = oauth.authorize_url(provider, state)
    except KeyError as e:
        hint = ""
        if provider == "slack" and request.app.state.app_env == "development":  # no https locally
            hint = (". Locally, paste your Slack token on the /connectors page instead"
                    " (docs/connectors/GUIDE.md, section 4)")
        raise HTTPException(503, f"{provider} sign-in is not configured: set {e.args[0]}{hint}") from e
    except ValueError as e:  # malformed TOKEN_ENCRYPTION_KEY
        raise HTTPException(503, f"{provider} sign-in is not configured: {e}") from e
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(STATE_COOKIE, f"{provider}.{state}", max_age=600, httponly=True,
                    samesite="lax", secure=_secure(), path="/oauth")
    return resp


@router.get("/oauth/{provider}/callback")
def callback(provider: str, request: Request, engine: Db, code: str | None = None, state: str | None = None,
             error: str | None = None):
    if provider not in oauth.PROVIDERS:
        raise HTTPException(404, f"unknown provider: {provider}")

    def finish(**result) -> RedirectResponse:
        frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
        resp = RedirectResponse(f"{frontend}/connectors?{urlencode(result)}", status_code=303)
        resp.delete_cookie(STATE_COOKIE, path="/oauth")
        return resp

    if error:  # the user clicked "Cancel", or the provider refused
        return finish(error="access_denied" if error == "access_denied" else "provider_error")
    expected = request.cookies.get(STATE_COOKIE, "")
    # bytes: compare_digest raises TypeError (a 500) on non-ASCII str
    if not (code and state and secrets.compare_digest(expected.encode(), f"{provider}.{state}".encode())):
        return finish(error="invalid_state")  # CSRF protection: this browser did not start this sign-in

    tokens = None
    try:
        tokens = oauth.exchange_code(provider, code)
        account = oauth.account(provider, tokens)
    except (oauth.OAuthError, httpx.HTTPError, KeyError) as e:
        log.warning("%s sign-in failed: %s", provider, e if isinstance(e, oauth.OAuthError) else type(e).__name__)
        # Account rejected (e.g. outside the company): drop the grant we were just given. Not on outages:
        # a Google revoke ends the whole grant, which may also back this person's stored connection.
        if tokens and isinstance(e, oauth.OAuthError) and e.status < 500:
            oauth.revoke(provider, tokens.access_token, tokens.refresh_token)
        codes = {oauth.NoCompany: "no_company", oauth.MissingPermission: "missing_permission"}
        return finish(error=codes.get(type(e), "provider_error"))

    linked = _link(request, engine, provider, account, tokens)
    if linked is None:
        return finish(error="account_mismatch")
    resp = finish(connected=provider)
    _set_session(resp, linked[1])
    return resp


@router.get("/connectors/{connector}/ping")
def ping(connector: str, engine: Db, current: User = Depends(current_user)):
    user = current.id
    _provider(connector)
    try:
        c = store.client(engine, user, connector)
        if connector == "slack":
            return {"ok": True, "as": c.auth_test()["user"]}
        if connector == "drive":
            return {"ok": True, "as": c.about().get(fields="user(emailAddress)").execute(num_retries=3)["user"]["emailAddress"]}
        path = "/rest/api/3/myself" if connector == "jira" else "/wiki/rest/api/user/current"
        return {"ok": True, "as": atlassian.request("GET", path, http=c).json()["displayName"]}
    except store.NotConnected as e:
        raise HTTPException(404, f"{connector} is not connected") from e
    except store.ReconnectNeeded as e:
        raise HTTPException(401, f"{connector} access expired: connect again") from e
    except (SlackApiError, HttpError, httpx.HTTPError, oauth.OAuthError) as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 401:  # revoked, or a scope missing
            raise HTTPException(401, f"{connector} refused the stored access: connect again") from e
        log.warning("%s ping failed: %s", connector, type(e).__name__)
        raise HTTPException(502, f"{connector} API call failed") from e


@router.delete("/connectors/{connector}", status_code=204)
def disconnect(connector: str, engine: Db, current: User = Depends(current_user)):
    user = current.id
    provider = _provider(connector)
    with engine.begin() as db:
        if tokens := store.delete_connection(db, user, provider):
            record_event(db, user, "connector_disconnected", {"provider": provider})
    if tokens and tokens[0]:  # revoke only after the delete is committed (and if the token was readable)
        oauth.revoke(provider, *tokens)
    return Response(status_code=204)


class SlackToken(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=500, pattern=r"^xoxp-[A-Za-z0-9-]+$")  # user tokens only


@dev_router.post("/connectors/slack")
def dev_connect_slack(body: SlackToken, request: Request, engine: Db):
    """Connect Slack with your own user token (xoxp-, from the Slack app's OAuth & Permissions page)
    instead of the OAuth redirect, so local development needs no https tunnel. Same checks as sign-in."""
    try:
        store.cipher()
    except (KeyError, ValueError) as e:
        raise HTTPException(503, f"slack is not configured: {e}") from e
    tokens = oauth.Tokens(body.token, None, None, "")
    try:
        account = oauth.account("slack", tokens)
    except oauth.NoCompany as e:
        raise HTTPException(403, "no_company: this Slack workspace belongs to no company you can join") from e
    except (oauth.OAuthError, httpx.HTTPError, KeyError) as e:
        log.warning("slack dev token rejected: %s", e if isinstance(e, oauth.OAuthError) else type(e).__name__)
        raise HTTPException(400, "Slack rejected the token") from e
    linked = _link(request, engine, "slack", account, tokens)
    if linked is None:
        raise HTTPException(409, "account_mismatch: this Slack account belongs to someone else")
    resp = JSONResponse({"connected": "slack", "as": account.name})
    _set_session(resp, linked[1])
    return resp

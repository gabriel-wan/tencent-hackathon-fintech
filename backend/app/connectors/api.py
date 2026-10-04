"""Connectors API (ADR-002): connect, list, call and disconnect each user's own accounts.

GET    /connectors                   the 4 connectors and whether you are connected
GET    /connectors/{id}/connect      redirects to the provider's sign-in page
GET    /oauth/{provider}/callback    provider redirects back here; stores the connection
GET    /connectors/{id}/ping         calls the API as you (proves the connection works)
DELETE /connectors/{id}              disconnects (Jira and Confluence share one Atlassian sign-in)

Signing in to the first connector also signs you in to the app (sessions: app/auth.py).
Database work happens in short transactions committed inside each handler, never across a
call to a provider, so no connection is held while waiting on the network.
"""

import logging
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from googleapiclient.errors import HttpError
from slack_sdk.errors import SlackApiError

from app import auth
from app.auth import MaybeUser, User
from app.connectors import atlassian, oauth, store
from app.db import Db

log = logging.getLogger(__name__)
router = APIRouter()

CONNECTORS = {  # connector id -> (OAuth provider, display name)
    "drive": ("google", "Google Drive"),
    "slack": ("slack", "Slack"),
    "jira": ("atlassian", "Jira"),
    "confluence": ("atlassian", "Confluence"),
}
STATE_COOKIE = "oauth_state"


def _provider(connector: str) -> str:
    if connector not in CONNECTORS:
        raise HTTPException(404, f"unknown connector: {connector}")
    return CONNECTORS[connector][0]


@router.get("/connectors")
def list_connectors(engine: Db, user: MaybeUser):
    with engine.connect() as db:
        connected = store.list_connections(db, user) if user else {}
    result = []
    for connector, (provider, name) in CONNECTORS.items():
        conn = connected.get(provider)
        if conn and provider == "atlassian" and not store.atlassian_site(conn["extra"], connector):
            conn = None  # signed in to Atlassian, but the site has no access to this product
        account = {"name": conn["account_name"], "email": conn["account_email"]} if conn else None
        result.append({"id": connector, "name": name, "connected": conn is not None, "account": account})
    return result


@router.get("/connectors/{connector}/connect")
def connect(connector: str):
    provider = _provider(connector)
    state = secrets.token_urlsafe(32)
    try:
        store.cipher()  # fail now, not after the user has signed in
        url = oauth.authorize_url(provider, state)
    except KeyError as e:
        raise HTTPException(503, f"{provider} sign-in is not configured: set {e.args[0]}") from e
    except ValueError as e:  # malformed TOKEN_ENCRYPTION_KEY
        raise HTTPException(503, f"{provider} sign-in is not configured: {e}") from e
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(STATE_COOKIE, f"{provider}.{state}", max_age=600, httponly=True,
                    samesite="lax", secure=auth.secure_cookies(), path="/oauth")
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
    if not (code and state and secrets.compare_digest(expected, f"{provider}.{state}")):
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
        return finish(error="provider_error")

    with engine.begin() as db:  # committed before the redirect is sent
        signed_in = auth.session_user(db, request.cookies.get(auth.SESSION_COOKIE))
        user = auth.find_user(db, account.email)
        owner = store.connection_owner(db, provider, account.id)
        # ADR-002: one person = one company email, and each external account belongs to one person.
        if (signed_in and signed_in != user) or (owner and owner != user):
            return finish(error="account_mismatch")
        user = user or auth.create_user(db, account.email)
        store.save_connection(db, user, provider, account, tokens)
        session = None if signed_in else auth.create_session(db, user)
    # TODO(ADR-007): write this to the audit log once it exists.
    log.info("audit connector_connected user=%s provider=%s account=%s", user, provider, account.id)

    resp = finish(connected=provider)
    if session:
        auth.set_session_cookie(resp, session)
    return resp


@router.get("/connectors/{connector}/ping")
def ping(connector: str, engine: Db, user: User):
    _provider(connector)
    try:
        if connector == "slack":
            return {"ok": True, "as": store.slack_client(engine, user).auth_test()["user"]}
        if connector == "drive":
            about = store.drive_service(engine, user).about().get(fields="user(emailAddress)").execute(num_retries=3)
            return {"ok": True, "as": about["user"]["emailAddress"]}
        path = "/rest/api/3/myself" if connector == "jira" else "/wiki/rest/api/user/current"
        with store.atlassian_client(engine, user, connector) as http:
            return {"ok": True, "as": atlassian.request("GET", path, http=http).json()["displayName"]}
    except store.NotConnected as e:
        raise HTTPException(404, f"{connector} is not connected") from e
    except store.ReconnectNeeded as e:
        raise HTTPException(401, f"{connector} access expired: connect again") from e
    except (SlackApiError, HttpError, httpx.HTTPError, oauth.OAuthError) as e:
        log.warning("%s ping failed: %s", connector, type(e).__name__)
        raise HTTPException(502, f"{connector} API call failed") from e


@router.delete("/connectors/{connector}", status_code=204)
def disconnect(connector: str, engine: Db, user: User):
    provider = _provider(connector)
    with engine.begin() as db:
        tokens = store.delete_connection(db, user, provider)
    if tokens:  # revoke only after the delete is committed
        oauth.revoke(provider, *tokens)
        log.info("audit connector_disconnected user=%s provider=%s", user, provider)
    return Response(status_code=204)


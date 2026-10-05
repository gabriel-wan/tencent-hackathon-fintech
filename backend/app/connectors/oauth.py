"""OAuth 2.0 sign-in for the connectors (ADR-002): users connect their own company accounts.

Providers: google (Drive), slack (Slack), atlassian (Jira + Confluence: one sign-in covers both).
Each needs <PROVIDER>_CLIENT_ID and <PROVIDER>_CLIENT_SECRET, and its app must list the
redirect URI `{APP_URL}/oauth/<provider>/callback`.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

from app import companies

log = logging.getLogger(__name__)

http = httpx.Client(timeout=15)  # replaced in tests


@dataclass(frozen=True)
class Provider:
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    scope_param: str = "scope"
    scope_sep: str = " "
    auth_params: dict = field(default_factory=dict)


PROVIDERS = {
    "google": Provider(
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        ("openid", "email", "https://www.googleapis.com/auth/drive.readonly"),  # no `profile`: the email is enough
        auth_params={"access_type": "offline", "prompt": "consent"},  # always return a refresh token
    ),
    "slack": Provider(
        "https://slack.com/oauth/v2/authorize",
        "https://slack.com/api/oauth.v2.access",
        ("channels:read", "channels:history", "groups:read", "groups:history", "users:read", "users:read.email"),
        scope_param="user_scope",  # a user token: the API acts as the person, not the bot
        scope_sep=",",
    ),
    "atlassian": Provider(
        "https://auth.atlassian.com/authorize",
        "https://auth.atlassian.com/oauth/token",
        (
            "read:jira-work", "read:jira-user",
            # Confluence v2 (spaces, pages) takes only granular scopes; the v1 calls (restrictions, group
            # members, search, current user) take classic ones.
            "read:space:confluence", "read:page:confluence",
            "read:confluence-content.all", "read:confluence-groups", "search:confluence", "read:confluence-user",
            "read:me", "offline_access",  # identity, and a refresh token
        ),
        auth_params={"audience": "api.atlassian.com", "prompt": "consent"},
    ),
}


class OAuthError(Exception):
    """The provider rejected a request. The message holds only error codes, never tokens."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status  # >= 500: the provider is having trouble, the grant may still be fine


class NoCompany(OAuthError):
    """The sign-in is valid but its workspace or site belongs to no company this person can join."""


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_at: int | None  # unix seconds; None = does not expire
    scopes: str


@dataclass
class Account:
    id: str
    email: str
    name: str
    extra: dict
    company_id: int | None  # the company this sign-in names (app/companies.py); None for Google


def app_url() -> str:
    # Required, no default: it also decides whether cookies are Secure (https).
    return os.environ["APP_URL"].rstrip("/")


def redirect_uri(provider: str) -> str:
    return f"{app_url()}/oauth/{provider}/callback"


def _client(provider: str) -> tuple[str, str]:
    prefix = provider.upper()
    return os.environ[f"{prefix}_CLIENT_ID"], os.environ[f"{prefix}_CLIENT_SECRET"]


def authorize_url(provider: str, state: str) -> str:
    p = PROVIDERS[provider]
    params = {
        "client_id": _client(provider)[0],
        "redirect_uri": redirect_uri(provider),
        "response_type": "code",
        "state": state,
        p.scope_param: p.scope_sep.join(p.scopes),
        **p.auth_params,
    }
    return f"{p.authorize_url}?{urlencode(params)}"


def _json(resp: httpx.Response, what: str):
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    if resp.is_error or (isinstance(payload, dict) and payload.get("ok") is False):
        error = payload.get("error", resp.status_code) if isinstance(payload, dict) else resp.status_code
        raise OAuthError(f"{what} failed: {error}", resp.status_code if resp.is_error else 400)
    return payload


def _token_request(provider: str, grant: dict) -> Tokens:
    client_id, secret = _client(provider)
    body = {"client_id": client_id, "client_secret": secret, **grant}
    url = PROVIDERS[provider].token_url
    resp = http.post(url, json=body) if provider == "atlassian" else http.post(url, data=body)
    payload = _json(resp, f"{provider} token request")
    src = payload.get("authed_user", payload)  # Slack nests user tokens under authed_user
    expires_in = src.get("expires_in")
    return Tokens(
        access_token=src["access_token"],
        refresh_token=src.get("refresh_token"),
        expires_at=int(time.time()) + int(expires_in) if expires_in else None,
        scopes=src.get("scope", ""),
    )


def exchange_code(provider: str, code: str) -> Tokens:
    return _token_request(provider, {"grant_type": "authorization_code", "code": code,
                                     "redirect_uri": redirect_uri(provider)})


def refresh(provider: str, refresh_token: str) -> Tokens:
    """New access token. Atlassian rotates refresh tokens, so callers must store the returned one."""
    return _token_request(provider, {"grant_type": "refresh_token", "refresh_token": refresh_token})


def _get(url: str, token: str, **params):
    return _json(http.get(url, headers={"Authorization": f"Bearer {token}"}, params=params), url)


def account(provider: str, tokens: Tokens) -> Account:
    """Who signed in, and their company (app/companies.py). The email links one person's accounts
    across providers (ADR-002).
    """
    token = tokens.access_token
    if provider == "google":
        me = _get("https://openidconnect.googleapis.com/v1/userinfo", token)
        if not me.get("email_verified"):
            raise OAuthError("google email not verified")
        # Google names no company (personal accounts have no domain): the user keeps theirs, or gets one
        # when they connect Slack or Atlassian, in any order.
        return Account(me["sub"], me["email"].lower(), me.get("name") or me["email"], {}, None)
    if provider == "slack":
        me = _get("https://slack.com/api/auth.test", token)
        user = _get("https://slack.com/api/users.info", token, user=me["user_id"])["user"]
        email = user.get("profile", {}).get("email")
        if not email:
            raise OAuthError("slack email missing")
        guest = bool(user.get("is_restricted") or user.get("is_ultra_restricted"))
        company = companies.for_slack(me["team_id"], me.get("team") or me["team_id"], email.lower(), create=not guest)
        if company is None:
            raise NoCompany("slack workspace belongs to no company you can join")
        return Account(me["user_id"], email.lower(), user.get("real_name") or user["name"],
                       {"team_id": me["team_id"], "team": me.get("team"), "guest": guest}, company)
    me = _get("https://api.atlassian.com/me", token)
    if me.get("email_verified") is False:
        raise OAuthError("atlassian email not verified")
    sites = _get("https://api.atlassian.com/oauth/token/accessible-resources", token)
    found = companies.for_atlassian(sites, me["email"].lower())
    if found is None:
        raise NoCompany("atlassian sign-in must grant exactly one site of your company")
    company, cloud_id = found
    return Account(me["account_id"], me["email"].lower(), me.get("name") or me["email"],
                   {"sites": [{k: s[k] for k in ("id", "url", "name", "scopes")} for s in sites if s["id"] == cloud_id]},
                   company)


def revoke(provider: str, access_token: str, refresh_token: str | None) -> None:
    """Best effort: tell the provider to drop the grant. Atlassian has no revoke endpoint."""
    try:
        if provider == "google":
            http.post("https://oauth2.googleapis.com/revoke", data={"token": refresh_token or access_token})
        elif provider == "slack":
            http.get("https://slack.com/api/auth.revoke", headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError as e:
        log.warning("%s revoke failed: %s", provider, type(e).__name__)

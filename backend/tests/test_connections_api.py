"""Connect / list / call / disconnect each user's own accounts (ADR-002), end to end through the API.

Providers are faked at the HTTP layer (httpx.MockTransport); the database is a SQLite file with a
fresh connection per use, so separate transactions really are separate (as on Postgres).
"""

import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool

from app import auth
from app.connectors import atlassian, drive, oauth, slack, store
from app.db import get_engine, metadata
from app.main import app

GOOGLE_TOKEN = "POST https://oauth2.googleapis.com/token"
GOOGLE_ME = "GET https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_REVOKE = "POST https://oauth2.googleapis.com/revoke"
SLACK_TOKEN = "POST https://slack.com/api/oauth.v2.access"
SLACK_ME = "GET https://slack.com/api/auth.test"
SLACK_USER = "GET https://slack.com/api/users.info"
SLACK_REVOKE = "GET https://slack.com/api/auth.revoke"
ATL_TOKEN = "POST https://auth.atlassian.com/oauth/token"
ATL_ME = "GET https://api.atlassian.com/me"
ATL_SITES = "GET https://api.atlassian.com/oauth/token/accessible-resources"
BOTH_PRODUCTS = ["read:jira-work", "read:confluence-content.all"]
PROVIDER_OF = {"drive": "google", "slack": "slack", "jira": "atlassian", "confluence": "atlassian"}


class FakeProviders:
    """Google, Slack and Atlassian OAuth endpoints. `routes` maps "METHOD url" to a JSON body or Response."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.routes = {
            GOOGLE_TOKEN: {"access_token": "g-access", "refresh_token": "g-refresh", "expires_in": 3600,
                           "scope": "openid email drive.readonly"},
            GOOGLE_ME: {"sub": "g-1", "email": "Alice@Corp.com", "email_verified": True, "name": "Alice"},
            GOOGLE_REVOKE: {},
            SLACK_TOKEN: {"ok": True, "authed_user": {"id": "U1", "access_token": "xoxp-alice", "scope": "users:read"},
                          "team": {"id": "T1", "name": "Corp"}},
            SLACK_ME: {"ok": True, "user_id": "U1", "team_id": "T1", "team": "Corp", "user": "alice"},
            SLACK_USER: {"ok": True, "user": {"name": "alice", "real_name": "Alice",
                                              "profile": {"email": "alice@corp.com"}}},
            SLACK_REVOKE: {"ok": True, "revoked": True},
            ATL_TOKEN: {"access_token": "a-access", "refresh_token": "a-refresh-1", "expires_in": 3600,
                        "scope": "read:jira-work"},
            ATL_ME: {"account_id": "A1", "email": "alice@corp.com", "name": "Alice", "email_verified": True},
            ATL_SITES: [{"id": "cloud-1", "url": "https://corp.atlassian.net", "name": "corp",
                         "scopes": BOTH_PRODUCTS}],
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes[f"{request.method} {request.url.copy_with(query=None)}"]
        return route if isinstance(route, httpx.Response) else httpx.Response(200, json=route)

    def sent(self, route: str) -> list[httpx.Request]:
        return [r for r in self.requests if f"{r.method} {r.url.copy_with(query=None)}" == route]


@pytest.fixture
def providers(monkeypatch):
    fake = FakeProviders()
    monkeypatch.setattr(oauth, "http", httpx.Client(transport=httpx.MockTransport(fake.handle)))
    for provider in ("GOOGLE", "SLACK", "ATLASSIAN"):
        monkeypatch.setenv(f"{provider}_CLIENT_ID", f"{provider.lower()}-client")
        monkeypatch.setenv(f"{provider}_CLIENT_SECRET", f"{provider.lower()}-secret")
    monkeypatch.setenv("APP_URL", "http://localhost:8000")
    monkeypatch.setenv("SLACK_TEAM_ID", "T1")  # the company workspace
    monkeypatch.setenv("ATLASSIAN_CLOUD_ID", "cloud-1")  # the company site
    return fake


@pytest.fixture
def engine(monkeypatch, tmp_path):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    eng = sa.create_engine(f"sqlite:///{tmp_path / 'test.db'}", poolclass=NullPool)
    metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine):
    app.dependency_overrides[get_engine] = lambda: engine
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def sign_in(client, connector, state=None):
    """Click "connect", then come back from the provider with a code. Returns the callback response."""
    resp = client.get(f"/connectors/{connector}/connect")
    assert resp.status_code == 302
    real_state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    return client.get(f"/oauth/{PROVIDER_OF[connector]}/callback",
                      params={"code": "the-code", "state": state or real_state})


def statuses(client):
    return {c["id"]: c["connected"] for c in client.get("/connectors").json()}


# ---- Starting a sign-in ----

@pytest.mark.parametrize(
    ("connector", "host", "expected"),
    [
        ("drive", "accounts.google.com", {"access_type": "offline", "prompt": "consent"}),
        ("slack", "slack.com", {"user_scope": ",".join(oauth.PROVIDERS["slack"].scopes)}),
        ("jira", "auth.atlassian.com", {"audience": "api.atlassian.com", "prompt": "consent"}),
    ],
)
def test_connect_redirects_to_provider(client, providers, connector, host, expected):
    resp = client.get(f"/connectors/{connector}/connect")
    url = urlparse(resp.headers["location"])
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    provider = PROVIDER_OF[connector]
    assert url.hostname == host
    assert params["redirect_uri"] == f"http://localhost:8000/oauth/{provider}/callback"
    assert params["client_id"] == f"{provider}-client"
    assert expected.items() <= params.items()
    cookie = resp.headers["set-cookie"]
    assert f"oauth_state={provider}.{params['state']}" in cookie
    assert "HttpOnly" in cookie and "Path=/oauth" in cookie and "Secure" not in cookie


def test_cookies_are_secure_on_https(client, providers, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://brain.example.com")
    resp = client.get("/connectors/drive/connect")
    assert "Secure" in resp.headers["set-cookie"]
    assert "redirect_uri=https%3A%2F%2Fbrain.example.com%2Foauth%2Fgoogle%2Fcallback" in resp.headers["location"]


@pytest.mark.parametrize("missing", ["APP_URL", "SLACK_CLIENT_ID", "SLACK_TEAM_ID", "TOKEN_ENCRYPTION_KEY"])
def test_connect_unconfigured_fails_before_sign_in(client, providers, monkeypatch, missing):
    monkeypatch.delenv(missing)
    resp = client.get("/connectors/slack/connect")
    assert resp.status_code == 503
    assert missing in resp.json()["detail"]


def test_connect_with_malformed_encryption_key(client, providers, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "not-a-fernet-key")
    store.cipher.cache_clear()
    assert client.get("/connectors/drive/connect").status_code == 503


def test_unknown_connector(client):
    assert client.get("/connectors/teams/connect").status_code == 404


# ---- Finishing a sign-in ----

def test_sign_in_connects_and_starts_a_session(client, providers, engine):
    resp = sign_in(client, "drive")
    assert resp.status_code == 303
    assert resp.headers["location"] == "http://localhost:3000/connectors?connected=google"
    assert "session=" in resp.headers["set-cookie"]

    listing = client.get("/connectors").json()
    assert statuses(client) == {"drive": True, "slack": False, "jira": False, "confluence": False}
    assert listing[0]["account"] == {"name": "Alice", "email": "alice@corp.com"}
    assert "g-access" not in str(listing) and "g-refresh" not in str(listing)

    with engine.connect() as conn:  # tokens are encrypted at rest
        row = conn.execute(sa.select(store.connections)).mappings().one()
    assert b"g-access" not in row["access_token"] and b"g-refresh" not in row["refresh_token"]

    exchange = providers.sent(GOOGLE_TOKEN)[0]
    assert parse_qs(exchange.content.decode())["grant_type"] == ["authorization_code"]


def test_one_person_links_all_connectors_by_email(client, providers, engine):
    for connector in ("drive", "slack", "jira"):
        assert "connected=" in sign_in(client, connector).headers["location"]
    assert statuses(client) == {"drive": True, "slack": True, "jira": True, "confluence": True}
    with engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(auth.users)).scalar() == 1
        assert conn.execute(sa.select(sa.func.count()).select_from(auth.sessions)).scalar() == 1



def test_principals_match_the_acl_formats(client, providers, engine):
    # The contract with search (docs/connectors/*.md section 5): a document is a candidate if its acl
    # holds one of these.
    for connector in ("drive", "slack", "jira"):
        sign_in(client, connector)
    with engine.connect() as conn:
        user = conn.execute(sa.select(auth.users.c.id)).scalar_one()
        assert store.principals(conn, user) == {
            "google:user:alice@corp.com", "google:domain:corp.com", "public",
            "slack:user:U1", "slack:members",
            "atlassian:user:A1",
        }
        assert store.principals(conn, uuid.uuid4()) == set()  # nothing connected: matches nothing


def test_atlassian_site_without_confluence(client, providers):
    providers.routes[ATL_SITES][0]["scopes"] = ["read:jira-work"]
    sign_in(client, "jira")
    assert statuses(client)["jira"] is True
    assert statuses(client)["confluence"] is False


def test_forged_state_is_rejected(client, providers):
    resp = sign_in(client, "drive", state="attacker-state")
    assert resp.headers["location"].endswith("error=invalid_state")
    assert "session=" not in resp.headers.get("set-cookie", "")
    assert providers.sent(GOOGLE_TOKEN) == []  # the code is never even exchanged


def test_callback_without_starting_sign_in_is_rejected(client, providers):
    resp = client.get("/oauth/google/callback", params={"code": "c", "state": "s"})
    assert resp.headers["location"].endswith("error=invalid_state")


def test_state_from_another_provider_is_rejected(client, providers):
    resp = client.get("/connectors/drive/connect")
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    resp = client.get("/oauth/slack/callback", params={"code": "c", "state": state})
    assert resp.headers["location"].endswith("error=invalid_state")


def test_user_cancels(client, providers):
    resp = client.get("/oauth/google/callback", params={"error": "access_denied"})
    assert resp.headers["location"].endswith("error=access_denied")


@pytest.mark.parametrize(
    ("route", "response"),
    [
        (GOOGLE_TOKEN, httpx.Response(400, json={"error": "invalid_grant"})),
        (GOOGLE_ME, {"sub": "g-1", "email": "alice@corp.com", "email_verified": False}),
        (GOOGLE_TOKEN, httpx.Response(502, text="<html>bad gateway</html>")),
    ],
)
def test_provider_failures_store_nothing(client, providers, route, response):
    providers.routes[route] = response
    resp = sign_in(client, "drive")
    assert resp.headers["location"].endswith("error=provider_error")
    assert statuses(client)["drive"] is False


def test_slack_error_is_a_failure_even_with_http_200(client, providers):
    providers.routes[SLACK_TOKEN] = {"ok": False, "error": "invalid_code"}
    assert sign_in(client, "slack").headers["location"].endswith("error=provider_error")


def test_slack_sign_in_from_another_workspace_is_rejected(client, providers):
    # Anyone can create a Slack workspace and put the victim's email on a profile there.
    providers.routes[SLACK_ME] = {**providers.routes[SLACK_ME], "team_id": "T-ATTACKER"}
    assert sign_in(client, "slack").headers["location"].endswith("error=provider_error")
    assert providers.sent(SLACK_USER) == []  # rejected before the email is even read
    assert statuses(client)["slack"] is False


def test_atlassian_sign_in_without_the_company_site_is_rejected(client, providers):
    providers.routes[ATL_SITES] = [{"id": "cloud-attacker", "url": "https://evil.atlassian.net", "name": "evil",
                                    "scopes": BOTH_PRODUCTS}]
    assert sign_in(client, "jira").headers["location"].endswith("error=provider_error")
    assert statuses(client)["jira"] is False


def test_other_sites_are_not_stored(client, providers, engine):
    providers.routes[ATL_SITES] = providers.routes[ATL_SITES] + [
        {"id": "cloud-other", "url": "https://other.atlassian.net", "name": "other", "scopes": BOTH_PRODUCTS}]
    sign_in(client, "jira")
    with engine.connect() as conn:
        extra = conn.execute(sa.select(store.connections.c.extra)).scalar()
    assert [s["id"] for s in extra["sites"]] == ["cloud-1"]


def test_external_account_stays_with_its_owner(client, providers, engine):
    sign_in(client, "slack")  # U1 belongs to alice
    client.post("/logout")
    providers.routes[SLACK_USER] = {"ok": True, "user": {"name": "a", "profile": {"email": "renamed@corp.com"}}}
    assert sign_in(client, "slack").headers["location"].endswith("error=account_mismatch")
    with engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(auth.users)).scalar() == 1


def test_cannot_attach_someone_elses_account(client, providers):
    sign_in(client, "drive")  # signed in as alice
    providers.routes[SLACK_USER] = {"ok": True, "user": {"name": "bob", "profile": {"email": "bob@corp.com"}}}
    resp = sign_in(client, "slack")
    assert resp.headers["location"].endswith("error=account_mismatch")
    assert statuses(client)["slack"] is False


# ---- Using a connection ----

def test_ping_requires_sign_in(client):
    assert client.get("/connectors/slack/ping").status_code == 401


def test_ping_not_connected(client, providers):
    sign_in(client, "drive")
    assert client.get("/connectors/slack/ping").status_code == 404


def fake_atlassian(monkeypatch, status=200):
    """Replace user_client with a fake site; returns the (product, cloud id, auth header, path) of each call."""
    seen = []

    def user_client(token, product, cloud_id):
        def handle(request):
            seen.append((product, cloud_id, request.headers["authorization"], request.url.path))
            return httpx.Response(status, json={"displayName": "Alice"})

        return httpx.Client(base_url=f"https://api.atlassian.com/ex/{product}/{cloud_id}",
                            headers={"Authorization": f"Bearer {token}"}, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(atlassian, "user_client", user_client)
    return seen


def test_ping_jira_and_confluence_call_the_users_site(client, providers, monkeypatch):
    sign_in(client, "jira")
    seen = fake_atlassian(monkeypatch)
    assert client.get("/connectors/jira/ping").json() == {"ok": True, "as": "Alice"}
    assert client.get("/connectors/confluence/ping").json() == {"ok": True, "as": "Alice"}
    assert seen == [
        ("jira", "cloud-1", "Bearer a-access", "/ex/jira/cloud-1/rest/api/3/myself"),
        ("confluence", "cloud-1", "Bearer a-access", "/ex/confluence/cloud-1/wiki/rest/api/user/current"),
    ]


def test_ping_slack_uses_the_users_token(client, providers, monkeypatch):
    sign_in(client, "slack")
    tokens = []

    class Slack:
        def auth_test(self):
            return {"user": "alice"}

    monkeypatch.setattr(slack, "client", lambda token: tokens.append(token) or Slack())
    assert client.get("/connectors/slack/ping").json() == {"ok": True, "as": "alice"}
    assert tokens == ["xoxp-alice"]


class FakeDrive:
    """service().about().get(...).execute(...) chain for the ping."""

    def about(self):
        return self

    def get(self, fields):
        return self

    def execute(self, num_retries):
        return {"user": {"emailAddress": "alice@corp.com"}}


def fake_drive(monkeypatch):
    """Replace drive.service; returns the access token each call was built with."""
    tokens = []
    monkeypatch.setattr(drive, "service", lambda creds: tokens.append(creds.token) or FakeDrive())
    return tokens


def test_ping_drive_uses_the_users_token(client, providers, monkeypatch):
    sign_in(client, "drive")
    tokens = fake_drive(monkeypatch)
    assert client.get("/connectors/drive/ping").json() == {"ok": True, "as": "alice@corp.com"}
    assert tokens == ["g-access"]


def expire_tokens(engine):
    with engine.begin() as conn:
        conn.execute(store.connections.update().values(expires_at=int(time.time()) - 1))


def test_expired_token_is_refreshed_and_rotation_is_stored(client, providers, engine, monkeypatch):
    sign_in(client, "jira")
    expire_tokens(engine)
    providers.routes[ATL_TOKEN] = {"access_token": "a-access-2", "refresh_token": "a-refresh-2", "expires_in": 3600}
    seen = fake_atlassian(monkeypatch)

    client.get("/connectors/jira/ping")
    client.get("/connectors/jira/ping")  # still fresh: no second refresh

    refreshes = providers.sent(ATL_TOKEN)[1:]  # [0] was the sign-in
    assert len(refreshes) == 1
    assert b'"refresh_token":"a-refresh-1"' in refreshes[0].content.replace(b" ", b"")
    assert [auth for _, _, auth, _ in seen] == ["Bearer a-access-2", "Bearer a-access-2"]
    with engine.connect() as conn:
        stored = conn.execute(sa.select(store.connections.c.refresh_token)).scalar()
    assert store._decrypt(stored) == "a-refresh-2"  # rotated token kept, or the next refresh would fail


def test_rotated_token_is_kept_even_when_the_api_call_then_fails(client, providers, engine, monkeypatch):
    sign_in(client, "jira")
    expire_tokens(engine)
    providers.routes[ATL_TOKEN] = {"access_token": "a-access-2", "refresh_token": "a-refresh-2", "expires_in": 3600}
    fake_atlassian(monkeypatch, status=500)
    assert client.get("/connectors/jira/ping").status_code == 502  # the request fails and rolls back...
    with engine.connect() as conn:
        stored = conn.execute(sa.select(store.connections.c.refresh_token)).scalar()
    assert store._decrypt(stored) == "a-refresh-2"  # ...but the spent refresh token was already replaced


def test_google_refresh_keeps_the_original_refresh_token(client, providers, engine, monkeypatch):
    sign_in(client, "drive")
    expire_tokens(engine)
    providers.routes[GOOGLE_TOKEN] = {"access_token": "g-access-2", "expires_in": 3600}  # no new refresh token
    tokens = fake_drive(monkeypatch)
    assert client.get("/connectors/drive/ping").status_code == 200
    assert tokens == ["g-access-2"]
    with engine.connect() as conn:
        stored = conn.execute(sa.select(store.connections.c.refresh_token)).scalar()
    assert store._decrypt(stored) == "g-refresh"


def test_rejected_refresh_asks_user_to_reconnect(client, providers, engine):
    sign_in(client, "drive")
    expire_tokens(engine)
    providers.routes[GOOGLE_TOKEN] = httpx.Response(400, json={"error": "invalid_grant"})
    resp = client.get("/connectors/drive/ping")
    assert resp.status_code == 401
    assert "connect again" in resp.json()["detail"]


def test_provider_outage_during_refresh_is_not_a_disconnect(client, providers, engine):
    sign_in(client, "drive")
    expire_tokens(engine)
    providers.routes[GOOGLE_TOKEN] = httpx.Response(503, text="unavailable")
    assert client.get("/connectors/drive/ping").status_code == 502  # try later, not "connect again"
    assert statuses(client)["drive"] is True


def test_ping_reports_api_failure_without_details(client, providers, monkeypatch):
    sign_in(client, "jira")
    fake_atlassian(monkeypatch, status=403)
    resp = client.get("/connectors/jira/ping")
    assert resp.status_code == 502
    assert resp.json() == {"detail": "jira API call failed"}


# ---- Disconnecting and signing out ----

def test_disconnect_removes_and_revokes(client, providers):
    sign_in(client, "drive")
    assert client.delete("/connectors/drive").status_code == 204
    assert statuses(client)["drive"] is False
    assert parse_qs(providers.sent(GOOGLE_REVOKE)[0].content.decode())["token"] == ["g-refresh"]


def test_disconnecting_jira_also_disconnects_confluence(client, providers):
    sign_in(client, "jira")
    client.delete("/connectors/jira")
    assert statuses(client) == {"drive": False, "slack": False, "jira": False, "confluence": False}


def test_disconnect_requires_sign_in(client):
    assert client.delete("/connectors/drive").status_code == 401


def test_logout_ends_the_session(client, providers):
    sign_in(client, "drive")
    assert client.post("/logout").status_code == 204
    assert statuses(client)["drive"] is False  # anonymous again
    assert client.get("/connectors/drive/ping").status_code == 401


def test_expired_session_is_ignored(client, providers, engine):
    sign_in(client, "drive")
    with engine.begin() as conn:
        conn.execute(auth.sessions.update().values(expires_at=int(time.time()) - 1))
    assert statuses(client)["drive"] is False

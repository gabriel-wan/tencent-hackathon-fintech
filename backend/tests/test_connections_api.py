"""Connect / list / call / disconnect each user's own accounts (ADR-002), end to end through the API.

Providers are faked at the HTTP layer (httpx.MockTransport). The database is the real test database
(migrated by conftest); handlers commit their own transactions, so its tables are emptied around each test.
"""

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from slack_sdk.errors import SlackApiError

from app.auth.principals import principals_for
from app.connectors import atlassian, drive, oauth, slack, store
from app.db import engine as db_engine
from app.db import owner_engine
from app.main import app, create_app

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
            GOOGLE_ME: {"sub": "g-1", "email": "Alice@Corp.com", "email_verified": True, "name": "Alice",
                        "hd": "corp.com"},
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


def add_company(name, slack_team, atlassian_cloud) -> int:
    with db_engine.begin() as conn:
        return conn.execute(
            sa.text("INSERT INTO companies (name, slack_team_id, atlassian_cloud_id) VALUES (:n, :s, :a) RETURNING id"),
            {"n": name, "s": slack_team, "a": atlassian_cloud},
        ).scalar_one()


@pytest.fixture
def providers(monkeypatch, engine):
    fake = FakeProviders()
    monkeypatch.setattr(oauth, "http", httpx.Client(transport=httpx.MockTransport(fake.handle)))
    for provider in ("GOOGLE", "SLACK", "ATLASSIAN"):
        monkeypatch.setenv(f"{provider}_CLIENT_ID", f"{provider.lower()}-client")
        monkeypatch.setenv(f"{provider}_CLIENT_SECRET", f"{provider.lower()}-secret")
    monkeypatch.setenv("APP_URL", "http://localhost:8000")
    # The company (its Slack workspace and Atlassian site) and alice, a member who has not connected yet.
    fake.company = add_company("Corp", "T1", "cloud-1")
    with db_engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO users (email, name, company_id) VALUES ('alice@corp.com', 'Alice', :c)"),
                     {"c": fake.company})
    return fake


def empty_tables():
    with owner_engine().begin() as conn:  # the app may not empty tables; also empties connections, sessions, user_principals
        conn.execute(sa.text("TRUNCATE users, companies CASCADE"))


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    empty_tables()
    yield db_engine
    empty_tables()


@pytest.fixture
def client(engine):
    return TestClient(app, follow_redirects=False)


def sign_in(client, connector, state=None):
    """Click "connect", then come back from the provider with a code. Returns the callback response."""
    resp = client.get(f"/connectors/{connector}/connect")
    assert resp.status_code == 302
    real_state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    return client.get(f"/oauth/{PROVIDER_OF[connector]}/callback",
                      params={"code": "the-code", "state": state or real_state})


def count(engine, table):
    with engine.connect() as conn:
        return conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()


def principals(engine):
    with engine.connect() as conn:
        return principals_for(conn, conn.execute(sa.text("SELECT id FROM users")).scalar_one())


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


@pytest.mark.parametrize(("connector", "missing"), [
    ("slack", "APP_URL"), ("slack", "SLACK_CLIENT_ID"), ("slack", "TOKEN_ENCRYPTION_KEY"), ("drive", "GOOGLE_CLIENT_ID"),
])
def test_connect_unconfigured_fails_before_sign_in(client, providers, monkeypatch, connector, missing):
    monkeypatch.delenv(missing)
    resp = client.get(f"/connectors/{connector}/connect")
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
    assert "ib_session=" in resp.headers["set-cookie"]

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
    assert count(engine, "users") == 1 and count(engine, "sessions") == 1


def test_principals_match_the_acl_formats(client, providers, engine):
    # The contract with search (docs/connectors/*.md section 5): a document is a candidate if its acl
    # holds one of these. They are written to user_principals, read by the query pipeline.
    for connector in ("drive", "slack", "jira"):
        sign_in(client, connector)
    assert principals(engine) == sorted({
        "google:user:alice@corp.com", "google:domain:corp.com", "public",
        "slack:user:U1", "slack:members",
        "atlassian:user:A1",
    })
    client.delete("/connectors/slack")  # disconnecting removes that tool's principals
    assert not [p for p in principals(engine) if p.startswith("slack:")]


@pytest.mark.parametrize("guest_flag", ["is_restricted", "is_ultra_restricted"])
def test_slack_guests_do_not_hold_slack_members(client, providers, engine, guest_flag):
    providers.routes[SLACK_USER]["user"][guest_flag] = True
    sign_in(client, "slack")
    assert principals(engine) == ["public", "slack:user:U1"]


def test_unknown_slack_guest_status_counts_as_guest():
    account = oauth.Account("U1", "alice@corp.com", "Alice", {"team_id": "T1"}, 1)  # no "guest" recorded
    assert store.principals("slack", account) == {"slack:user:U1"}


def test_atlassian_site_without_confluence(client, providers):
    providers.routes[ATL_SITES][0]["scopes"] = ["read:jira-work"]
    sign_in(client, "jira")
    assert statuses(client)["jira"] is True
    assert statuses(client)["confluence"] is False


def test_forged_state_is_rejected(client, providers):
    resp = sign_in(client, "drive", state="attacker-state")
    assert resp.headers["location"].endswith("error=invalid_state")
    assert "ib_session=" not in resp.headers.get("set-cookie", "")
    assert providers.sent(GOOGLE_TOKEN) == []  # the code is never even exchanged


def test_callback_without_starting_sign_in_is_rejected(client, providers):
    resp = client.get("/oauth/google/callback", params={"code": "c", "state": "s"})
    assert resp.headers["location"].endswith("error=invalid_state")


def test_non_ascii_state_is_rejected_not_a_crash(client, providers):
    client.get("/connectors/drive/connect")
    resp = client.get("/oauth/google/callback", params={"code": "c", "state": "é"})
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


def test_google_sign_in_without_drive_access_is_rejected_and_revoked(client, providers):
    providers.routes[GOOGLE_TOKEN] = {"access_token": "g-access", "refresh_token": "g-refresh", "expires_in": 3600,
                                      "scope": "openid https://www.googleapis.com/auth/userinfo.email"}
    resp = sign_in(client, "drive")
    assert resp.headers["location"].endswith("error=missing_permission")
    assert statuses(client)["drive"] is False
    assert len(providers.sent(GOOGLE_REVOKE)) == 1  # the useless grant is dropped, so the next Connect asks again


def test_slack_error_is_a_failure_even_with_http_200(client, providers):
    providers.routes[SLACK_TOKEN] = {"ok": False, "error": "invalid_code"}
    assert sign_in(client, "slack").headers["location"].endswith("error=provider_error")


def test_slack_sign_in_from_another_workspace_cannot_take_over_a_user(client, providers, engine):
    # Anyone can create a Slack workspace and put the victim's email on a profile there.
    providers.routes[SLACK_ME] = {**providers.routes[SLACK_ME], "team_id": "T-ATTACKER"}
    assert sign_in(client, "slack").headers["location"].endswith("error=no_company")
    assert statuses(client)["slack"] is False
    assert count(engine, "companies") == 1  # alice is not an admin: she cannot add a workspace either


def test_connections_work_in_any_order_drive_first(client, providers, engine):
    # Google names no company: Drive connects, and the person has no company (sees nothing) until
    # Slack names one. Then they join it, as its admin since Corp has none yet.
    providers.routes[GOOGLE_ME] = {"sub": "g-2", "email": "bob@corp.com", "email_verified": True}
    assert sign_in(client, "drive").headers["location"].endswith("connected=google")
    assert users_by_company(engine)["bob@corp.com"] == (None, False)
    providers.routes[SLACK_ME] = {**providers.routes[SLACK_ME], "user_id": "U2"}
    providers.routes[SLACK_USER] = {"ok": True, "user": {"name": "bob", "profile": {"email": "bob@corp.com"}}}
    assert sign_in(client, "slack").headers["location"].endswith("connected=slack")
    assert users_by_company(engine)["bob@corp.com"] == (providers.company, True)
    assert statuses(client) == {"drive": True, "slack": True, "jira": False, "confluence": False}


def users_by_company(engine):
    with engine.connect() as conn:
        return {e: (c, a) for e, c, a in conn.execute(sa.text("SELECT email, company_id, is_admin FROM users"))}


def sign_in_from_new_workspace(client, providers, email, user_id="U2", guest=False):
    client.delete("/api/session")
    providers.routes[SLACK_ME] = {**providers.routes[SLACK_ME], "user_id": user_id, "team_id": "T2", "team": "Other"}
    providers.routes[SLACK_USER] = {"ok": True, "user": {"name": email, "profile": {"email": email},
                                                         "is_restricted": guest}}
    return sign_in(client, "slack").headers["location"]


def test_first_sign_in_from_a_new_workspace_creates_the_company_and_its_admin(client, providers, engine):
    assert sign_in_from_new_workspace(client, providers, "bob@other.com").endswith("connected=slack")
    assert sign_in_from_new_workspace(client, providers, "carol@other.com", "U3").endswith("connected=slack")
    with engine.connect() as conn:
        other = conn.execute(sa.text("SELECT id FROM companies WHERE slack_team_id = 'T2'")).scalar_one()
    assert users_by_company(engine) == {"alice@corp.com": (providers.company, False),
                                        "bob@other.com": (other, True), "carol@other.com": (other, False)}
    with engine.connect() as conn:  # who joined, and who was made admin, is in the audit log
        events = conn.execute(sa.text("SELECT a.payload->>'made_admin' FROM audit_events a JOIN users u "
                                      "ON u.id = a.user_id ORDER BY a.id")).scalars().all()
    assert events == ["true", "false"]


def test_a_slack_guest_cannot_start_a_company(client, providers, engine):
    assert sign_in_from_new_workspace(client, providers, "guest@agency.com", guest=True).endswith("error=no_company")
    assert count(engine, "companies") == 1


def test_a_slack_guest_never_becomes_admin_even_of_a_company_without_one(client, providers, engine):
    # e.g. the company's first sign-in was refused at linking, so it has no members yet.
    other = add_company("Other", "T2", None)
    assert sign_in_from_new_workspace(client, providers, "guest@agency.com", guest=True).endswith("connected=slack")
    assert users_by_company(engine)["guest@agency.com"] == (other, False)


def test_a_person_cannot_join_a_second_company(client, providers, engine):
    sign_in(client, "drive")  # alice@corp.com, in Corp
    add_company("Other", "T2", None)
    assert sign_in_from_new_workspace(client, providers, "alice@corp.com").endswith("error=account_mismatch")
    assert users_by_company(engine) == {"alice@corp.com": (providers.company, False)}


def test_admin_adds_their_companys_atlassian_site(client, providers, engine):
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE companies SET atlassian_cloud_id = NULL"))
        conn.execute(sa.text("UPDATE users SET is_admin = true"))
    assert sign_in(client, "jira").headers["location"].endswith("connected=atlassian")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT atlassian_cloud_id FROM companies")).scalar() == "cloud-1"


def test_atlassian_listing_one_site_once_per_product_is_one_site(client, providers, engine):
    # What Atlassian really returns for an app with Jira and Confluence scopes: the same site twice.
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE companies SET atlassian_cloud_id = NULL"))
        conn.execute(sa.text("UPDATE users SET is_admin = true"))
    site = {"id": "cloud-1", "url": "https://corp.atlassian.net", "name": "corp"}
    providers.routes[ATL_SITES] = [{**site, "scopes": ["read:jira-work"]},
                                   {**site, "scopes": ["read:confluence-content.all"]}]
    assert sign_in(client, "jira").headers["location"].endswith("connected=atlassian")
    assert statuses(client)["jira"] is True and statuses(client)["confluence"] is True


def test_atlassian_never_starts_a_company(client, providers, engine):
    # Atlassian can't tell a contractor from an employee: whoever signs in first must not become admin.
    providers.routes[ATL_ME] = {**providers.routes[ATL_ME], "account_id": "A9", "email": "contractor@agency.com"}
    providers.routes[ATL_SITES] = [{"id": "cloud-9", "url": "https://new.atlassian.net", "name": "new",
                                    "scopes": BOTH_PRODUCTS}]
    assert sign_in(client, "jira").headers["location"].endswith("error=no_company")
    assert count(engine, "companies") == 1


def test_atlassian_sign_in_granting_several_new_sites_is_rejected(client, providers):
    providers.routes[ATL_ME] = {**providers.routes[ATL_ME], "email": "new@elsewhere.com"}
    providers.routes[ATL_SITES] = [{"id": f"cloud-{i}", "url": "https://x.atlassian.net", "name": "x",
                                    "scopes": BOTH_PRODUCTS} for i in (8, 9)]
    assert sign_in(client, "jira").headers["location"].endswith("error=no_company")


def test_outage_after_sign_in_does_not_revoke(client, providers):
    # Revoking would end the person's whole Google grant, including a connection they already have.
    providers.routes[GOOGLE_ME] = httpx.Response(502, text="bad gateway")
    assert sign_in(client, "drive").headers["location"].endswith("error=provider_error")
    assert providers.sent(GOOGLE_REVOKE) == []


def test_atlassian_sign_in_without_the_company_site_is_rejected(client, providers):
    providers.routes[ATL_SITES] = [{"id": "cloud-attacker", "url": "https://evil.atlassian.net", "name": "evil",
                                    "scopes": BOTH_PRODUCTS}]
    assert sign_in(client, "jira").headers["location"].endswith("error=no_company")
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
    client.delete("/api/session")
    providers.routes[SLACK_USER] = {"ok": True, "user": {"name": "a", "profile": {"email": "renamed@corp.com"}}}
    assert sign_in(client, "slack").headers["location"].endswith("error=account_mismatch")
    assert count(engine, "users") == 1


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


def test_ping_slack_with_a_revoked_token_asks_to_connect_again(client, providers, monkeypatch):
    sign_in(client, "slack")

    class Slack:  # what Slack answers after Disconnect (auth.revoke) or a reinstall
        def auth_test(self):
            raise SlackApiError("token_revoked", {"ok": False, "error": "token_revoked"})

    monkeypatch.setattr(slack, "client", lambda token: Slack())
    resp = client.get("/connectors/slack/ping")
    assert resp.status_code == 401 and "connect again" in resp.json()["detail"]


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


def test_provider_refusing_the_token_asks_user_to_reconnect(client, providers, monkeypatch):
    sign_in(client, "confluence")
    fake_atlassian(monkeypatch, status=401)  # e.g. a scope added after this sign-in
    resp = client.get("/connectors/confluence/ping")
    assert resp.status_code == 401
    assert "connect again" in resp.json()["detail"]


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

def test_disconnect_removes_and_revokes(client, providers, engine):
    sign_in(client, "drive")
    assert client.delete("/connectors/drive").status_code == 204
    assert statuses(client)["drive"] is False
    assert parse_qs(providers.sent(GOOGLE_REVOKE)[0].content.decode())["token"] == ["g-refresh"]
    with engine.connect() as conn:
        assert conn.execute(sa.text(  # audit_events is append-only: this test's user only
            "SELECT event_type FROM audit_events a JOIN users u ON u.id = a.user_id ORDER BY a.id")).scalars().all() == [
            "connector_connected", "connector_disconnected"]


def test_changed_encryption_key_means_connect_again_not_a_crash(client, providers, monkeypatch):
    sign_in(client, "drive")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    store.cipher.cache_clear()
    resp = client.get("/connectors/drive/ping")
    assert resp.status_code == 401 and "connect again" in resp.json()["detail"]
    assert client.delete("/connectors/drive").status_code == 204  # still removable; nothing readable to revoke
    assert statuses(client)["drive"] is False and providers.sent(GOOGLE_REVOKE) == []


def test_disconnecting_jira_also_disconnects_confluence(client, providers):
    sign_in(client, "jira")
    client.delete("/connectors/jira")
    assert statuses(client) == {"drive": False, "slack": False, "jira": False, "confluence": False}


def test_disconnect_requires_sign_in(client):
    assert client.delete("/connectors/drive").status_code == 401


def test_connector_sign_in_is_the_app_session(client, providers):
    sign_in(client, "drive")
    assert client.get("/api/me").json() == {"email": "alice@corp.com", "name": "Alice", "is_admin": False}
    assert client.delete("/api/session").status_code == 204
    assert statuses(client)["drive"] is False  # anonymous again
    assert client.get("/connectors/drive/ping").status_code == 401


def test_expired_session_is_ignored(client, providers, engine):
    sign_in(client, "drive")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE sessions SET expires_at = now() - interval '1 second'"))
    assert statuses(client)["drive"] is False


# ---- Development only: connect Slack with a pasted user token (no https tunnel) ----

DEV_SLACK = "/api/dev/connectors/slack"


def test_dev_slack_token_route_exists_only_in_development(engine, providers):
    assert TestClient(create_app("production")).post(DEV_SLACK, json={"token": "xoxp-alice"}).status_code == 404


def test_dev_slack_token_connects_like_sign_in(engine, providers):
    dev = TestClient(create_app("development"))
    resp = dev.post(DEV_SLACK, json={"token": "xoxp-alice"})
    assert resp.json() == {"connected": "slack", "as": "Alice"}
    assert "ib_session=" in resp.headers["set-cookie"]
    assert statuses(dev)["slack"] is True
    assert principals(engine) == ["public", "slack:members", "slack:user:U1"]
    assert providers.sent(SLACK_ME)[0].headers["authorization"] == "Bearer xoxp-alice"


def test_dev_slack_token_from_another_workspace_is_rejected(engine, providers):
    providers.routes[SLACK_ME] = {**providers.routes[SLACK_ME], "team_id": "T-ATTACKER"}
    resp = TestClient(create_app("development")).post(DEV_SLACK, json={"token": "xoxp-mallory"})
    assert resp.status_code == 403
    assert count(engine, "users") == 1  # only alice, unchanged


def test_dev_slack_rejects_anything_but_a_user_token(engine, providers):
    resp = TestClient(create_app("development")).post(DEV_SLACK, json={"token": "xoxb-bot\r\nX-Evil: 1"})
    assert resp.status_code == 422
    assert providers.sent(SLACK_ME) == []


@pytest.mark.parametrize("url", ["https://brain.example.com", "http://203.0.113.7:8000", "http://brain.example.com"])
def test_development_mode_refuses_any_server_deployment(monkeypatch, url):
    # The dev routes sign anyone in as anyone: a plain-http demo server must refuse them too.
    monkeypatch.setenv("APP_URL", url)
    with pytest.raises(RuntimeError):
        create_app("development")


def test_development_mode_runs_on_localhost(monkeypatch):
    monkeypatch.setenv("APP_URL", "http://localhost:8000")
    assert TestClient(create_app("development")).get("/api/dev/users").status_code == 200


@pytest.mark.parametrize(("app_env", "hinted"), [("development", True), ("production", False)])
def test_slack_connect_unconfigured_points_to_the_token_route_in_development(engine, providers, monkeypatch,
                                                                             app_env, hinted):
    monkeypatch.delenv("SLACK_CLIENT_ID")  # the local setup: no Slack OAuth app
    detail = TestClient(create_app(app_env)).get("/connectors/slack/connect").json()["detail"]
    assert "SLACK_CLIENT_ID" in detail
    assert ("paste your Slack token" in detail) is hinted

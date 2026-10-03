import os

# app.db builds its engine at import; it never connects in tests (get_engine is overridden).
for _key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_DB"):
    os.environ.setdefault(_key, "unused-in-tests")

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.connectors import atlassian, slack, store  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    """Tests never reach real APIs: drop connector env vars and any cached client or key."""
    for key in list(os.environ):
        if key.startswith(("ATLASSIAN_", "GOOGLE_", "SLACK_", "APP_URL", "FRONTEND_URL", "TOKEN_ENCRYPTION_KEY")):
            monkeypatch.delenv(key)
    atlassian.client.cache_clear()
    slack.bot.cache_clear()
    store.cipher.cache_clear()


@pytest.fixture
def atlassian_api(monkeypatch):
    """install(handler) routes Atlassian calls to handler(request) -> Response; returns (sent, sleeps)."""
    sent, sleeps = [], []

    def install(handler):
        def record(request):
            sent.append(request)
            return handler(request)

        c = httpx.Client(base_url="https://example.atlassian.net", transport=httpx.MockTransport(record))
        monkeypatch.setattr(atlassian, "client", lambda: c)
        monkeypatch.setattr(atlassian.time, "sleep", sleeps.append)
        return sent, sleeps

    return install

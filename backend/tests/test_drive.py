"""Drive credentials (admin and user), ping and live access check. No real API calls."""

import json
import re
from urllib.parse import unquote

import httplib2
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpMockSequence

from app.connectors import drive


@pytest.fixture(scope="module")
def sa_json():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return json.dumps({
        "type": "service_account",
        "client_email": "brain@test-project.iam.gserviceaccount.com",
        "private_key": pem.decode(),
        "token_uri": "https://oauth2.googleapis.com/token",
    })


@pytest.fixture
def workspace(monkeypatch, sa_json):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", sa_json)


@pytest.fixture
def oauth_app(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")


def test_personal_mode_by_default():
    assert drive.mode() == "personal"


def test_personal_admin_requires_refresh_token():
    with pytest.raises(KeyError, match="GOOGLE_REFRESH_TOKEN"):
        drive.admin_credentials()


def test_personal_admin_is_the_admins_oauth_sign_in(oauth_app, monkeypatch):
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "admin-token")
    creds = drive.admin_credentials()
    assert (creds.refresh_token, creds.client_id, creds.token) == ("admin-token", "id", None)


def test_personal_admin_requires_oauth_app(monkeypatch):
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "admin-token")
    with pytest.raises(KeyError, match="GOOGLE_CLIENT_ID"):
        drive.admin_credentials()


def test_workspace_impersonates_admin_by_default(workspace, monkeypatch):
    monkeypatch.setenv("GOOGLE_ADMIN_EMAIL", "admin@company.com")
    creds = drive.admin_credentials()
    assert drive.mode() == "workspace"
    assert creds._subject == "admin@company.com"
    assert creds.scopes == drive.SCOPES


def test_workspace_explicit_subject_wins(workspace, monkeypatch):
    monkeypatch.setenv("GOOGLE_ADMIN_EMAIL", "admin@company.com")
    assert drive.admin_credentials("sara@company.com")._subject == "sara@company.com"


def test_workspace_without_admin_acts_as_service_account(workspace):
    assert drive.admin_credentials()._subject is None


def test_workspace_rejects_malformed_json(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{not json")
    with pytest.raises(ValueError):
        drive.admin_credentials()


def fake_service(monkeypatch, http):
    monkeypatch.setattr(drive, "service", lambda credentials: build("drive", "v3", http=http, static_discovery=True))
    monkeypatch.setattr("googleapiclient.http.time.sleep", lambda s: None)


ABOUT = json.dumps({"user": {"emailAddress": "sara@company.com"}})


@pytest.fixture
def personal_admin(oauth_app, monkeypatch):
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "admin-token")


def test_ping(personal_admin, monkeypatch):
    fake_service(monkeypatch, HttpMockSequence([({"status": "200"}, ABOUT)]))
    assert drive.ping() == "as sara@company.com (personal mode)"


def test_ping_retries_server_error(personal_admin, monkeypatch):
    fake_service(monkeypatch, HttpMockSequence([({"status": "503"}, ""), ({"status": "200"}, ABOUT)]))
    assert drive.ping() == "as sara@company.com (personal mode)"


def test_ping_raises_on_client_error(personal_admin, monkeypatch):
    body = json.dumps({"error": {"message": "Invalid Credentials"}})
    fake_service(monkeypatch, HttpMockSequence([({"status": "401"}, body)]))
    with pytest.raises(HttpError):
        drive.ping()


class FakeBatchHttp:
    """Answers Drive batch requests (multipart/mixed): each file gets the status in `statuses`."""

    def __init__(self, statuses):
        self.statuses, self.batches = statuses, []

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        assert uri.endswith("/batch/drive/v3")
        body = body.decode() if isinstance(body, bytes) else body
        content_ids = re.findall(r"Content-ID: <([^>]+)>", body)
        self.batches.append(len(content_ids))
        parts = []
        for content_id in content_ids:
            file_id = unquote(content_id.rsplit("+", 1)[1].strip())
            status = self.statuses.get(file_id, 404)
            payload = json.dumps({"id": file_id} if status == 200 else {"error": {"code": status}})
            parts.append(
                f"--B\r\nContent-Type: application/http\r\nContent-ID: <response-{content_id}>\r\n\r\n"
                f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n\r\n{payload}\r\n"
            )
        content = ("".join(parts) + "--B--").encode()
        return httplib2.Response({"status": "200", "content-type": "multipart/mixed; boundary=B"}), content


def test_can_read_keeps_only_files_the_user_can_open(monkeypatch):
    http = FakeBatchHttp({"budget": 200, "runbook": 200, "secret": 404, "team-only": 403, "flaky": 500})
    fake_service(monkeypatch, http)
    ids = ["budget", "secret", "runbook", "team-only", "flaky", "budget"]
    assert drive.can_read(object(), ids) == {"budget", "runbook"}  # 403/404 denied, 500 denied (deny by default)
    assert http.batches == [5]  # one request for all files, duplicates removed


def test_can_read_splits_large_requests(monkeypatch):
    ids = [f"f{i}" for i in range(drive.BATCH_LIMIT + 1)]
    http = FakeBatchHttp(dict.fromkeys(ids, 200))
    fake_service(monkeypatch, http)
    assert drive.can_read(object(), ids) == set(ids)
    assert http.batches == [drive.BATCH_LIMIT, 1]


def test_can_read_denies_everything_when_the_request_fails(monkeypatch):
    class Down:
        def request(self, *args, **kwargs):
            raise OSError("network down")

    fake_service(monkeypatch, Down())
    assert drive.can_read(object(), ["budget"]) == set()


def test_can_read_nothing_to_check(monkeypatch):
    http = FakeBatchHttp({})
    fake_service(monkeypatch, http)
    assert drive.can_read(object(), []) == set()
    assert http.batches == []

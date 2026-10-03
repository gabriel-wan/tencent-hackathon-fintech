"""Google Drive connector. API details: docs/connectors/GOOGLE_DRIVE.md.

admin_credentials() reads the company Drive inside the admin's boundary (ADR-002): Workspace
service account if GOOGLE_SERVICE_ACCOUNT_JSON is set, otherwise the admin's own OAuth sign-in
(GOOGLE_REFRESH_TOKEN). A user's own credentials come from store.google_credentials().
"""

import json
import logging
import os
from collections.abc import Iterable

from google.oauth2 import credentials as oauth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/admin.directory.group.member.readonly",
]
BATCH_LIMIT = 100  # Drive's maximum calls per batch request


def mode() -> str:
    return "workspace" if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") else "personal"


def admin_credentials(subject: str | None = None):
    """Admin credentials; in Workspace mode act as `subject` (defaults to GOOGLE_ADMIN_EMAIL)."""
    if mode() == "personal":
        return oauth.Credentials(
            None,
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
        )  # scopes come from the refresh token itself
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    subject = subject or os.environ.get("GOOGLE_ADMIN_EMAIL")
    return creds.with_subject(subject) if subject else creds


def service(credentials):
    # Cheap (~5 ms, bundled discovery doc), so build one per use.
    # ponytail: not thread-safe; never share one service across threads.
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def ping() -> str:
    about = service(admin_credentials()).about().get(fields="user(emailAddress)").execute(num_retries=3)
    return f"as {about['user']['emailAddress']} ({mode()} mode)"


def can_read(credentials, file_ids: Iterable[str]) -> set[str]:
    """Live check (ADR-003): which of these files the owner of `credentials` can read right now.

    Asks Google directly (files.get as that user), batched into one request per 100 files.
    Deny by default: 403/404 means no access; any other error also leaves the file out.
    """
    ids = list(dict.fromkeys(file_ids))
    allowed: set[str] = set()

    def collect(file_id, _response, error):
        if error is None:
            allowed.add(file_id)
        elif not (isinstance(error, HttpError) and error.status_code in (403, 404)):
            log.warning("Drive check for %s failed, denying: %s", file_id, error)

    drive = service(credentials)
    for start in range(0, len(ids), BATCH_LIMIT):
        batch = drive.new_batch_http_request(callback=collect)
        for file_id in ids[start : start + BATCH_LIMIT]:
            batch.add(drive.files().get(fileId=file_id, fields="id", supportsAllDrives=True), request_id=file_id)
        try:
            batch.execute()
        except Exception:  # deny by default: auth, network or parse failure drops the whole batch
            log.exception("Drive batch check failed, denying %d files", len(ids[start : start + BATCH_LIMIT]))
    return allowed

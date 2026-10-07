"""Google Drive connector. API details: docs/connectors/GOOGLE_DRIVE.md.

Every call uses one person's own Google sign-in (store.client): the company admin's for sync and the
scope list, the asking user's for the live check.
"""

import logging
from collections.abc import Callable, Iterable, Iterator

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

BATCH_LIMIT = 100  # Drive's maximum calls per batch request
FOLDER = "application/vnd.google-apps.folder"
EXPORT = {  # Google-native type -> plain-text export
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}
FILE_FIELDS = "nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink, permissions(type, emailAddress, domain))"


def service(credentials):
    # Cheap (~5 ms, bundled discovery doc), so build one per use.
    # ponytail: not thread-safe; never share one service across threads.
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _list(drive, q: str, fields: str) -> Iterator[dict]:
    token = None
    while True:
        resp = drive.files().list(q=q, fields=fields, pageSize=100, pageToken=token, supportsAllDrives=True,
                                  includeItemsFromAllDrives=True).execute(num_retries=3)
        yield from resp.get("files", [])
        if not (token := resp.get("nextPageToken")):
            return


def scopes(drive) -> list[dict]:
    """Folders this person can see, for the admin to choose the boundary from."""
    return [{"id": f["id"], "title": f["name"]}
            for f in _list(drive, f"mimeType = '{FOLDER}' and trashed = false", "nextPageToken, files(id, name)")]


def acl(permissions: list[dict]) -> list[str]:
    """Drive sharing -> ACL principals (docs/connectors/GOOGLE_DRIVE.md section 5)."""
    held = set()
    for p in permissions:
        email = p.get("emailAddress", "").lower()  # missing for e.g. a deleted account: it can't read anyway
        if p["type"] == "user" and email:
            held.add(f"google:user:{email}")
        elif p["type"] == "group" and email:
            # ponytail: a group widens to its domain (the live check trims); expanding members needs
            # Directory API admin scopes. Members outside that domain are missed until then.
            held.add(f"google:domain:{email.split('@')[1]}")
        elif p["type"] == "domain":
            held.add(f"google:domain:{p['domain'].lower()}")
        elif p["type"] == "anyone":
            held.add("public")
    return sorted(held)


def _text(drive, f: dict) -> str | None:
    try:
        if f["mimeType"] in EXPORT:
            data = drive.files().export(fileId=f["id"], mimeType=EXPORT[f["mimeType"]]).execute(num_retries=3)
        elif f["mimeType"].startswith("text/"):
            data = drive.files().get_media(fileId=f["id"], supportsAllDrives=True).execute(num_retries=3)
        else:
            return None  # ponytail: PDFs and Office files are skipped; add text extraction when needed
    except HttpError as e:  # e.g. a Doc over Drive's 10 MB export limit: skip it, never fail the whole folder
        if e.status_code >= 500 or e.status_code == 429:
            raise  # Drive trouble: retry the folder next run
        log.info("Drive file %s skipped: %s", f["id"], e.status_code)
        return None
    return data.decode("utf-8", "replace")


def fetch(drive, folder: str, changed: Callable[[str, str], bool] = lambda *_: True,
          scope: str | None = None) -> Iterator[dict]:
    """One document per file in the folder and its subfolders. Text is downloaded only for files that
    `changed(source_id, updated_at)`; the others get `text` None (sharing is refreshed either way)."""
    for f in _list(drive, f"'{folder}' in parents and trashed = false", FILE_FIELDS):
        if f["mimeType"] == FOLDER:
            yield from fetch(drive, f["id"], changed, scope or folder)
            continue
        # No sharing list: the admin may not share this file, or it is in a shared drive (Drive never lists
        # permissions there). Never guess an ACL. ponytail: read shared drives' permissions.list when needed.
        if "permissions" not in f:
            log.info("Drive file %s skipped: its sharing is not visible", f["id"])
            continue
        text = None
        if changed(f["id"], f["modifiedTime"]) and not (text := _text(drive, f)):
            continue
        principals = acl(f["permissions"])
        yield {
            "source": "drive",
            "source_id": f["id"],
            "scope_id": scope or folder,
            "title": f["name"],
            "url": f["webViewLink"],
            "updated_at": f["modifiedTime"],
            "acl": principals,
            "text": text,
            "metadata": {"overshared": "public" in principals},
        }


def can_read(drive, file_ids: Iterable[str]) -> set[str]:
    """Live check (ADR-003): which of these files the service's owner can read right now.

    Asks Google directly (files.get as that user), batched into one request per 100 files.
    Deny by default: 403/404 means no access; any other error also leaves the file out. Trashed files
    are denied too (files.get still returns them).
    """
    ids = list(dict.fromkeys(file_ids))
    allowed: set[str] = set()

    def collect(file_id, response, error):
        if error is None:
            if not response.get("trashed"):
                allowed.add(file_id)
        elif not (isinstance(error, HttpError) and error.status_code in (403, 404)):
            log.warning("Drive check for %s failed, denying: %s", file_id, error)

    for start in range(0, len(ids), BATCH_LIMIT):
        batch = drive.new_batch_http_request(callback=collect)
        for file_id in ids[start : start + BATCH_LIMIT]:
            batch.add(drive.files().get(fileId=file_id, fields="id,trashed", supportsAllDrives=True),
                      request_id=file_id)
        try:
            batch.execute()
        except Exception:  # deny by default: auth, network or parse failure drops the whole batch
            log.exception("Drive batch check failed, denying %d files", len(ids[start : start + BATCH_LIMIT]))
    return allowed

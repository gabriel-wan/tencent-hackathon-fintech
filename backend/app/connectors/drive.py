"""Google Drive connector. API details: docs/connectors/reference/GOOGLE_DRIVE.md.

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
PERMISSION = "type, emailAddress, domain, role, view, inheritedPermissionsDisabled, permissionDetails(inherited)"
FILE_FIELDS = f"nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink, driveId, permissions({PERMISSION}))"
PERMISSION_FIELDS = f"nextPageToken, permissions({PERMISSION})"
HANDLER_ROLES = {"owner", "organizer", "fileOrganizer", "writer"}  # may change the file, not only read it


def service(credentials):
    # Cheap (~5 ms, bundled discovery doc), so build one per use. Not thread-safe: never share one.
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
    """Drive sharing -> ACL principals (docs/connectors/reference/GOOGLE_DRIVE.md section 5)."""
    held = set()
    for p in permissions:
        email = p.get("emailAddress", "").lower()  # missing for e.g. a deleted account: it can't read anyway
        if p["type"] == "user" and email:
            held.add(f"google:user:{email}")
        elif p["type"] == "group" and email:
            # A group widens to its domain (the live check trims); members outside that domain are missed.
            held.add(f"google:domain:{email.split('@')[1]}")
        elif p["type"] == "domain":
            held.add(f"google:domain:{p['domain'].lower()}")
        elif p["type"] == "anyone":
            held.add("public")
    return sorted(held)


def _direct(p: dict) -> bool:
    return any(d.get("inherited") is False for d in p.get("permissionDetails", []))


def handlers(permissions: list[dict]) -> list[str]:
    """Need-to-Know Shield (ADR-010): people who own or edit the file see its identifiers unmasked.
    Named people only: an edit share to a group, domain or "anyone" never clears anyone. Every shared-drive
    contributor inherits edit on every file, so an inherited edit counts only for owners and organizers
    (the drive's managers); others need the file shared with them directly. No details: treated as direct."""
    return sorted({f"google:user:{p['emailAddress'].lower()}" for p in permissions
                   if p["type"] == "user" and p.get("role") in HANDLER_ROLES and p.get("emailAddress")
                   and (p["role"] in ("owner", "organizer") or "permissionDetails" not in p or _direct(p))})


def _opens(p: dict) -> bool:
    """Whether a permission lets its holder open the file. In a limited-access folder, inherited entries stay on
    the list but only show the folder's name; owners, organizers and people added directly still open it."""
    if p.get("view") == "metadata":
        return False
    if p.get("inheritedPermissionsDisabled") and p.get("role") not in ("owner", "organizer"):
        return _direct(p)
    return True


def _indexable(f: dict) -> bool:
    return f["mimeType"] in EXPORT or f["mimeType"].startswith("text/")


def _shared_drive_permissions(drive, file_ids: list[str]) -> dict[str, list[dict]]:
    """Full sharing lists (GOOGLE_DRIVE.md 4.5) of shared-drive files, which files.list never fills: drive
    members (inherited) and people the file is shared with directly; fetch keeps only those who can open it.
    Batched like can_read. A refused list (403/404) leaves the file out; any other error fails the folder,
    so it is retried next run instead of its files being dropped."""
    found: dict[str, list[dict]] = {}
    pages: dict[str, str] = {}
    failures: list[Exception] = []

    def collect(file_id, response, error):
        if error is None:
            found[file_id] = response.get("permissions", [])
            if token := response.get("nextPageToken"):
                pages[file_id] = token
        elif isinstance(error, HttpError) and error.status_code in (403, 404):
            log.info("Drive file %s skipped: its sharing is not visible", file_id)
        else:
            failures.append(error)

    def request(file_id, token=None):
        return drive.permissions().list(fileId=file_id, fields=PERMISSION_FIELDS, pageSize=100, pageToken=token,
                                        supportsAllDrives=True)

    for start in range(0, len(file_ids), BATCH_LIMIT):
        batch = drive.new_batch_http_request(callback=collect)
        for file_id in file_ids[start : start + BATCH_LIMIT]:
            batch.add(request(file_id), request_id=file_id)
        batch.execute()
    if failures:
        raise failures[0]
    for file_id, token in pages.items():  # rare: more than 100 entries
        while token:
            resp = request(file_id, token).execute(num_retries=3)
            found[file_id] += resp.get("permissions", [])
            token = resp.get("nextPageToken")
    return found


def _text(drive, f: dict) -> str | None:
    try:
        if f["mimeType"] in EXPORT:
            data = drive.files().export(fileId=f["id"], mimeType=EXPORT[f["mimeType"]]).execute(num_retries=3)
        elif f["mimeType"].startswith("text/"):
            data = drive.files().get_media(fileId=f["id"], supportsAllDrives=True).execute(num_retries=3)
        else:
            return None
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
    files = list(_list(drive, f"'{folder}' in parents and trashed = false", FILE_FIELDS))
    shared = _shared_drive_permissions(drive, [f["id"] for f in files if f.get("driveId") and "permissions" not in f
                                               and f["mimeType"] != FOLDER and _indexable(f)])
    for f in files:
        if f["mimeType"] == FOLDER:
            yield from fetch(drive, f["id"], changed, scope or folder)
            continue
        # No sharing list: the admin may not share this file (or, in a shared drive, may not read its list).
        # Never guess an ACL.
        if (permissions := f.get("permissions", shared.get(f["id"]))) is None:
            if "driveId" not in f:
                log.info("Drive file %s skipped: its sharing is not visible", f["id"])
            continue
        permissions = [p for p in permissions if _opens(p)]
        text = None
        if changed(f["id"], f["modifiedTime"]) and not (text := _text(drive, f)):
            continue
        principals = acl(permissions)
        yield {
            "source": "drive",
            "source_id": f["id"],
            "scope_id": scope or folder,
            "title": f["name"],
            "url": f["webViewLink"],
            "updated_at": f["modifiedTime"],
            "acl": principals,
            "text": text,
            "metadata": {"overshared": "public" in principals, "need_to_know": handlers(permissions)},
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

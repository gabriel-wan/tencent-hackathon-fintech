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
FILE_FIELDS = ("nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink, "
               "permissions(type, emailAddress, domain, role))")
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


MAX_DEPTH = 30  # folder nesting followed when looking for a folder's ancestors (Drive allows ~100; real ones are shallow)


MY_DRIVE, SHARED_WITH_ME = "my-drive", "shared-with-me"  # `drive_id`s of the two groups that aren't shared drives


def _shared_drive_names(drive) -> dict[str, str]:
    """Shared drive ID -> its name, for the drive headings. A failure only costs the names, never the list."""
    names: dict[str, str] = {}
    token = None
    try:
        while True:
            resp = drive.drives().list(pageSize=100, pageToken=token, fields="nextPageToken, drives(id, name)") \
                .execute(num_retries=3)
            names.update({d["id"]: d["name"] for d in resp.get("drives", [])})
            if not (token := resp.get("nextPageToken")):
                return names
    except HttpError as e:
        log.info("Drive shared drive names unavailable: %s", e.status_code)
        return names


def scopes(drive) -> list[dict]:
    """Folders this person can see, for the admin to choose the boundary from. Each has its `parent` (None at
    the top, or when the parent isn't one of these folders), its `path`, the names of the folders above it
    ("Finance / 2026"), so same-named folders can be told apart, and the drive it is in: `drive_id` (a shared
    drive's ID, MY_DRIVE or SHARED_WITH_ME) and `drive`, its name for the page's headings."""
    folders = list(_list(drive, f"mimeType = '{FOLDER}' and trashed = false",
                         "nextPageToken, files(id, name, parents, driveId, ownedByMe)"))
    by_id = {f["id"]: f for f in folders}
    shared = _shared_drive_names(drive) if any(f.get("driveId") for f in folders) else {}

    def parent(f: dict) -> str | None:
        p = (f.get("parents") or [None])[0]
        return p if p in by_id else None

    def path(f: dict) -> str:
        names, seen, p = [], {f["id"]}, parent(f)
        while p and p not in seen and len(names) < MAX_DEPTH:  # `seen`: never loop on odd data
            seen.add(p)
            names.append(by_id[p]["name"])
            p = parent(by_id[p])
        return " / ".join(reversed(names))

    def where(f: dict) -> tuple[str, str]:
        if f.get("driveId"):
            return f["driveId"], shared.get(f["driveId"], "Shared drive")
        return (MY_DRIVE, "My Drive") if f.get("ownedByMe") else (SHARED_WITH_ME, "Shared with me")

    return [{"id": f["id"], "title": f["name"], "parent": parent(f), "path": path(f),
             "drive_id": where(f)[0], "drive": where(f)[1]} for f in folders]


def ancestors(drive, folder_id: str, parent_of: dict[str, str | None] | None = None) -> list[str]:
    """The folders above this one, nearest first, as far as this person can see. Used to keep the boundary from
    holding a folder and a folder inside it (sync already includes subfolders; both would fight over the files).

    `parent_of`: a cache shared by every chain in one request, so a parent several folders share is asked once.
    Only a 404 (a parent this person can't see) ends the chain. A 403 is not a "no": Drive also uses it for rate
    limits, so it raises, and the caller refuses the change rather than let an overlap through unchecked."""
    parent_of = {} if parent_of is None else parent_of
    found: list[str] = []
    current = folder_id
    for _ in range(MAX_DEPTH):
        if current not in parent_of:
            try:
                meta = drive.files().get(fileId=current, fields="parents", supportsAllDrives=True).execute(num_retries=3)
            except HttpError as e:
                if e.status_code != 404:
                    raise
                meta = {}
            parent_of[current] = (meta.get("parents") or [None])[0]
        parent = parent_of[current]
        if not parent or parent in found or parent == folder_id:
            break
        current = parent
        found.append(current)
    return found


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


def handlers(permissions: list[dict]) -> list[str]:
    """Need-to-Know Shield (ADR-010): people who own or edit the file see its identifiers unmasked.
    Named people only: an edit share to a group, domain or "anyone" never clears anyone."""
    return sorted({f"google:user:{p['emailAddress'].lower()}" for p in permissions
                   if p["type"] == "user" and p.get("role") in HANDLER_ROLES and p.get("emailAddress")})


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
    for f in _list(drive, f"'{folder}' in parents and trashed = false", FILE_FIELDS):
        if f["mimeType"] == FOLDER:
            yield from fetch(drive, f["id"], changed, scope or folder)
            continue
        # No sharing list: the admin may not share this file, or it is in a shared drive (Drive never lists
        # permissions there). Never guess an ACL.
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
            "metadata": {"overshared": "public" in principals, "need_to_know": handlers(f["permissions"])},
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

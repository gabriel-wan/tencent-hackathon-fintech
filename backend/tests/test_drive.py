"""Drive connector: fetch (files and ACL) and the live access check. No real API calls."""

import json
import re
from urllib.parse import unquote

import httplib2
import pytest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.connectors import drive


def test_acl_maps_each_kind_of_sharing():
    assert drive.acl([
        {"type": "user", "emailAddress": "Alice@Corp.com"},
        {"type": "group", "emailAddress": "finance@corp.com"},  # widened to its domain (live check trims)
        {"type": "domain", "domain": "partner.com"},
        {"type": "anyone"},
        {"type": "user"},  # e.g. a deleted account: no email, skipped rather than failing the folder
    ]) == ["google:domain:corp.com", "google:domain:partner.com", "google:user:alice@corp.com", "public"]


class Call:
    def __init__(self, result):
        self.result = result

    def execute(self, num_retries=0):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeDrive:
    """files().list / export / get_media over a small tree: folder F1 holds a doc, a PDF, a file whose
    sharing is hidden from the caller, and subfolder F2 with a text file."""

    FILES = {
        "F1": [{"id": "doc", "name": "Runbook", "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-10-01T05:00:00.000Z", "webViewLink": "https://docs/doc",
                "permissions": [{"type": "anyone"}]},
               {"id": "pdf", "name": "Scan", "mimeType": "application/pdf", "permissions": [],
                "modifiedTime": "2026-10-01T05:00:00.000Z"},
               {"id": "hidden", "name": "Secret", "mimeType": "text/plain"},
               {"id": "F2", "name": "Sub", "mimeType": drive.FOLDER}],
        "F2": [{"id": "txt", "name": "Notes", "mimeType": "text/plain", "modifiedTime": "2026-10-02T05:00:00.000Z",
                "webViewLink": "https://docs/txt", "permissions": [{"type": "user", "emailAddress": "ben@corp.com", "role": "writer"}]}],
    }

    def files(self):
        return self

    def list(self, q, **kwargs):
        return Call({"files": self.FILES[re.match(r"'(\w+)' in parents", q)[1]]})

    def export(self, fileId, mimeType):
        return Call(b"Step 1: fail over")

    def get_media(self, fileId, **kwargs):
        return Call(b"Notes text")


@pytest.mark.security
def test_only_named_owners_and_editors_have_need_to_know():
    assert drive.handlers([
        {"type": "user", "emailAddress": "Ann@corp.com", "role": "owner"},
        {"type": "user", "emailAddress": "ben@corp.com", "role": "writer"},
        {"type": "user", "emailAddress": "cat@corp.com", "role": "reader"},
        {"type": "user", "emailAddress": "dan@corp.com", "role": "commenter"},
        {"type": "domain", "domain": "corp.com", "role": "writer"},
        {"type": "anyone", "role": "writer"},
        {"type": "group", "emailAddress": "eng@corp.com", "role": "writer"},
    ]) == ["google:user:ann@corp.com", "google:user:ben@corp.com"]


@pytest.mark.security
def test_shared_drive_contributors_need_the_file_shared_directly():
    inherited, direct = [{"inherited": True}], [{"inherited": True}, {"inherited": False}]
    assert drive.handlers([
        {"type": "user", "emailAddress": "ann@corp.com", "role": "organizer", "permissionDetails": inherited},
        {"type": "user", "emailAddress": "ben@corp.com", "role": "writer", "permissionDetails": inherited},
        {"type": "user", "emailAddress": "cat@corp.com", "role": "fileOrganizer", "permissionDetails": inherited},
        {"type": "user", "emailAddress": "dan@corp.com", "role": "writer", "permissionDetails": direct},
    ]) == ["google:user:ann@corp.com", "google:user:dan@corp.com"]


def test_fetch_walks_subfolders_and_skips_what_it_cannot_index():
    docs = {d["source_id"]: d for d in drive.fetch(FakeDrive(), "F1")}
    assert set(docs) == {"doc", "txt"}  # PDF has no text extraction; hidden sharing is never guessed
    assert docs["doc"]["acl"] == ["public"] and docs["doc"]["metadata"] == {"overshared": True, "need_to_know": []}
    assert docs["txt"] == {
        "source": "drive", "source_id": "txt", "scope_id": "F1", "title": "Notes", "url": "https://docs/txt",
        "updated_at": "2026-10-02T05:00:00.000Z", "acl": ["google:user:ben@corp.com"], "text": "Notes text",
        "metadata": {"overshared": False, "need_to_know": ["google:user:ben@corp.com"]},
    }  # scope is the boundary folder, not the subfolder


def test_a_file_drive_cannot_export_is_skipped_not_fatal():
    fake = FakeDrive()

    def too_large(**_):
        raise HttpError(httplib2.Response({"status": "403"}), b'{"error": {"message": "exportSizeLimitExceeded"}}')

    fake.export = too_large
    assert [d["source_id"] for d in drive.fetch(fake, "F1")] == ["txt"]  # the rest of the folder still syncs


def test_unchanged_files_are_not_downloaded_again():
    fake = FakeDrive()
    fake.export = fake.get_media = lambda **_: pytest.fail("an unchanged file was downloaded")
    stored = {"doc", "txt"}  # the PDF was never stored (no text), so it is never "unchanged"
    docs = {d["source_id"]: d for d in drive.fetch(fake, "F1", lambda source_id, _: source_id not in stored)}
    assert set(docs) == stored and all(d["text"] is None for d in docs.values())
    assert docs["txt"]["acl"] == ["google:user:ben@corp.com"]  # sharing still refreshed


def http_error(status):
    return HttpError(httplib2.Response({"status": str(status)}), b"{}")


class FakeBatch:
    """new_batch_http_request: runs each added request, reporting its result or error to the callback."""

    def __init__(self, callback):
        self.callback, self.added = callback, []

    def add(self, request, request_id):
        self.added.append((request_id, request))

    def execute(self):
        for request_id, request in self.added:
            try:
                self.callback(request_id, request.execute(), None)
            except HttpError as e:
                self.callback(request_id, None, e)


class FakeSharedDrive(FakeDrive):
    """Folder SD in shared drive D1. files.list never includes `permissions` there; permissions.list
    returns each file's full list: drive members (inherited) plus anything shared directly."""

    MEMBERS = [{"type": "user", "emailAddress": "ann@corp.com", "role": "organizer"},
               {"type": "user", "emailAddress": "ben@corp.com", "role": "reader"}]
    FILES = {"SD": [
        {"id": file_id, "name": file_id, "mimeType": "application/pdf" if file_id == "scan" else "text/plain",
         "driveId": "D1", "modifiedTime": "2026-10-01T05:00:00.000Z", "webViewLink": f"https://docs/{file_id}"}
        for file_id in ("team", "outside", "locked", "open", "scan")
    ]}
    SHARING = {
        "team": MEMBERS,
        "outside": MEMBERS + [{"type": "user", "emailAddress": "eve@partner.com", "role": "reader"}],
        # A limited-access folder: Google still lists inherited members, marked as unable to open it.
        "locked": [{**MEMBERS[0], "inheritedPermissionsDisabled": True},  # organizers always open it
                   {**MEMBERS[1], "inheritedPermissionsDisabled": True, "permissionDetails": [{"inherited": True}]},
                   {"type": "user", "emailAddress": "dan@corp.com", "role": "reader", "view": "metadata"},
                   {"type": "user", "emailAddress": "cat@corp.com", "role": "reader",
                    "inheritedPermissionsDisabled": True,  # but also added to the folder directly:
                    "permissionDetails": [{"inherited": True}, {"inherited": False}]}],
        "open": MEMBERS + [{"type": "anyone", "role": "reader"}],
    }

    def __init__(self, sharing=None):
        self.sharing, self.asked = dict(self.SHARING if sharing is None else sharing), []

    def permissions(self):
        return self

    def list(self, q=None, fileId=None, pageToken=None, **kwargs):
        if fileId is None:
            return super().list(q, **kwargs)
        assert kwargs["supportsAllDrives"]
        self.asked.append(fileId)
        answer = self.sharing.get(fileId, http_error(404))
        if isinstance(answer, dict):  # pages: {None: first page, token: next page}
            return Call(answer[pageToken])
        return Call(answer if isinstance(answer, Exception) else {"permissions": answer})

    def new_batch_http_request(self, callback):
        return FakeBatch(callback)


def shared_drive_acls(fake=None):
    return {d["source_id"]: d["acl"] for d in drive.fetch(fake or FakeSharedDrive(), "SD")}


@pytest.mark.security
def test_a_shared_drive_member_is_allowed_and_a_non_member_is_not():
    assert shared_drive_acls()["team"] == ["google:user:ann@corp.com", "google:user:ben@corp.com"]


@pytest.mark.security
def test_a_shared_drive_file_shared_with_an_outsider_allows_the_outsider():
    assert "google:user:eve@partner.com" in shared_drive_acls()["outside"]


@pytest.mark.security
def test_a_limited_access_folder_denies_drive_members_not_on_it():
    assert shared_drive_acls()["locked"] == ["google:user:ann@corp.com", "google:user:cat@corp.com"]


@pytest.mark.security
def test_a_shared_drive_file_open_to_anyone_is_overshared():
    docs = {d["source_id"]: d for d in drive.fetch(FakeSharedDrive(), "SD")}
    assert docs["open"]["metadata"] == {"overshared": True, "need_to_know": ["google:user:ann@corp.com"]}
    assert docs["team"]["metadata"]["overshared"] is False


def test_shared_drive_sharing_is_asked_only_for_files_that_can_be_indexed():
    fake = FakeSharedDrive()
    list(drive.fetch(fake, "SD"))
    assert sorted(fake.asked) == ["locked", "open", "outside", "team"]  # not the PDF


@pytest.mark.security
def test_a_shared_drive_file_whose_sharing_is_refused_is_skipped():
    fake = FakeSharedDrive({**FakeSharedDrive.SHARING, "locked": http_error(403)})
    assert set(shared_drive_acls(fake)) == {"team", "outside", "open"}  # never guessed


def test_a_drive_outage_fails_the_folder_instead_of_dropping_its_files():
    fake = FakeSharedDrive({**FakeSharedDrive.SHARING, "team": http_error(500)})
    with pytest.raises(HttpError):
        list(drive.fetch(fake, "SD"))  # sync then keeps the stored files and retries next run


def test_a_long_shared_drive_sharing_list_is_read_to_the_end():
    fake = FakeSharedDrive({**FakeSharedDrive.SHARING, "team": {
        None: {"permissions": FakeSharedDrive.MEMBERS[:1], "nextPageToken": "p2"},
        "p2": {"permissions": FakeSharedDrive.MEMBERS[1:]},
    }})
    assert shared_drive_acls(fake)["team"] == ["google:user:ann@corp.com", "google:user:ben@corp.com"]


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
            trashed = status == "trashed"  # files.get still answers 200 for a file in the trash
            status = 200 if trashed else status
            payload = json.dumps({"id": file_id, "trashed": trashed} if status == 200 else {"error": {"code": status}})
            parts.append(
                f"--B\r\nContent-Type: application/http\r\nContent-ID: <response-{content_id}>\r\n\r\n"
                f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n\r\n{payload}\r\n"
            )
        content = ("".join(parts) + "--B--").encode()
        return httplib2.Response({"status": "200", "content-type": "multipart/mixed; boundary=B"}), content


def service(http):
    return build("drive", "v3", http=http, static_discovery=True)


def test_can_read_keeps_only_files_the_user_can_open():
    http = FakeBatchHttp({"budget": 200, "runbook": 200, "secret": 404, "team-only": 403, "flaky": 500})
    ids = ["budget", "secret", "runbook", "team-only", "flaky", "budget"]
    assert drive.can_read(service(http), ids) == {"budget", "runbook"}  # 403/404 denied, 500 denied (deny by default)
    assert http.batches == [5]  # one request for all files, duplicates removed


@pytest.mark.security
def test_can_read_denies_a_trashed_file_before_the_next_sync():
    http = FakeBatchHttp({"runbook": 200, "old-runbook": "trashed"})
    assert drive.can_read(service(http), ["runbook", "old-runbook"]) == {"runbook"}


def test_can_read_splits_large_requests():
    ids = [f"f{i}" for i in range(drive.BATCH_LIMIT + 1)]
    http = FakeBatchHttp(dict.fromkeys(ids, 200))
    assert drive.can_read(service(http), ids) == set(ids)
    assert http.batches == [drive.BATCH_LIMIT, 1]


def test_can_read_denies_everything_when_the_request_fails():
    class Down:
        def request(self, *args, **kwargs):
            raise OSError("network down")

    assert drive.can_read(service(Down()), ["budget"]) == set()


def test_can_read_nothing_to_check():
    http = FakeBatchHttp({})
    assert drive.can_read(service(http), []) == set()
    assert http.batches == []

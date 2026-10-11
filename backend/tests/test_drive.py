"""Drive connector: fetch (files and ACL) and the live access check. No real API calls."""

import json
from types import SimpleNamespace
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


class FolderTree:
    """files().list for folders and files().get for parents, over: Finance > 2026 > Payroll, and a top-level
    Eng; Hidden's parent exists but this person can't see it."""

    FOLDERS = {"FIN": ("Finance", None), "Y26": ("2026", "FIN"), "PAY": ("Payroll", "Y26"), "ENG": ("Eng", None),
               "HID": ("Hidden child", "SECRET")}
    WHERE = {"ENG": {"driveId": "SD1"}, "HID": {"ownedByMe": False}}  # Eng in a shared drive; HID shared with me

    def files(self):
        return self

    def drives(self):
        return SimpleNamespace(list=lambda **_: Call({"drives": [{"id": "SD1", "name": "Engineering team"}]}))

    def list(self, q, fields, **kwargs):
        assert "parents" in fields and "driveId" in fields  # the listing must ask for parents and drives
        return Call({"files": [{"id": i, "name": n, **({"parents": [p]} if p else {}),
                                **self.WHERE.get(i, {"ownedByMe": True})}
                               for i, (n, p) in self.FOLDERS.items()]})

    def get(self, fileId, fields, **kwargs):
        if fileId == "SECRET":
            raise HttpError(httplib2.Response({"status": 404}), b"not found")
        parent = self.FOLDERS[fileId][1]
        return Call({"parents": [parent]} if parent else {})


def test_scopes_carry_each_folders_parent_and_path():
    by_id = {s["id"]: s for s in drive.scopes(FolderTree())}
    assert by_id["PAY"] == {"id": "PAY", "title": "Payroll", "parent": "Y26", "path": "Finance / 2026",
                            "drive_id": "my-drive", "drive": "My Drive"}
    assert (by_id["ENG"]["drive_id"], by_id["ENG"]["drive"]) == ("SD1", "Engineering team")
    assert by_id["HID"]["drive"] == "Shared with me"
    assert by_id["FIN"]["parent"] is None and by_id["FIN"]["path"] == ""
    assert by_id["HID"]["parent"] is None  # its parent isn't one this person can see: shown at the top


def test_ancestors_walk_up_as_far_as_this_person_can_see():
    assert drive.ancestors(FolderTree(), "PAY") == ["Y26", "FIN"]
    assert drive.ancestors(FolderTree(), "FIN") == []
    assert drive.ancestors(FolderTree(), "HID") == ["SECRET"]  # the hidden parent ends the chain, no error


def test_ancestors_share_one_cache_and_a_403_is_not_a_no():
    tree, calls = FolderTree(), []
    get = tree.get

    def counted(fileId, fields, **kwargs):
        calls.append(fileId)
        return get(fileId, fields, **kwargs)

    tree.get = counted
    cache: dict = {}
    drive.ancestors(tree, "PAY", cache)
    drive.ancestors(tree, "Y26", cache)  # its chain is already known
    assert calls == ["PAY", "Y26", "FIN"]

    class Limited(FolderTree):
        def get(self, fileId, fields, **kwargs):
            raise HttpError(httplib2.Response({"status": 403}), b"rate limit")

    with pytest.raises(HttpError):
        drive.ancestors(Limited(), "PAY")


def test_folders_still_list_when_shared_drive_names_fail():
    class NoNames(FolderTree):
        def drives(self):
            def fail(**_):
                raise HttpError(httplib2.Response({"status": 403}), b"forbidden")
            return SimpleNamespace(list=lambda **_: SimpleNamespace(execute=lambda **__: fail()))

    by_id = {s["id"]: s for s in drive.scopes(NoNames())}
    assert by_id["ENG"]["drive"] == "Shared drive" and len(by_id) == 5

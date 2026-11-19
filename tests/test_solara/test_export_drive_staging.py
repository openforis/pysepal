"""Direct workspace exports stage in a dedicated Drive folder, like SEPAL."""

import asyncio
import re
import threading
from types import SimpleNamespace

import httpx
import pytest
from eeclient.exceptions import EERestException

from pysepal.solara.components import export_engine
from pysepal.solara.components.export_engine import submit_export_request
from pysepal.solara.components.export_models import ExportRequest

FOLDER = "application/vnd.google-apps.folder"


def _call(fn):
    return SimpleNamespace(execute=fn)


class _FakeDrive:
    """The Drive v3 ``files()`` calls the engine makes, over an in-memory tree."""

    def __init__(self, user="demo-user"):
        self.items = {}
        self.service = self
        self.user = user

    def files(self):
        return self

    def add(self, name, parent, mime="image/tiff"):
        item_id = f"id{len(self.items)}"
        self.items[item_id] = {"id": item_id, "name": name, "mimeType": mime, "parents": [parent]}
        return item_id

    def children(self, parent):
        return [i for i in self.items.values() if parent in i["parents"]]

    def path_of(self, item_id):
        parts = []
        while item_id != "root":
            item = self.items[item_id]
            parts.insert(0, item["name"])
            item_id = item["parents"][0]
        return "/".join(parts)

    def list(self, q, **_):
        name = re.search(r"name = '([^']*)'", q)
        mime = re.search(r"mimeType = '([^']*)'", q)
        files = [
            i
            for i in self.children(re.search(r"'([^']*)' in parents", q).group(1))
            if (not name or i["name"] == name.group(1))
            and (not mime or i["mimeType"] == mime.group(1))
        ]
        return _call(lambda: {"files": files})

    def create(self, body, **_):
        return _call(lambda: {"id": self.add(body["name"], body["parents"][0], body["mimeType"])})

    def delete(self, fileId):
        def remove():
            for child in self.children(fileId):
                self.delete(child["id"]).execute()
            del self.items[fileId]

        return _call(remove)


class _FakeGee:
    def __init__(self, drive, state="COMPLETED"):
        self.drive = drive
        self.state = state
        self.folders = []

    async def export_image_to_drive_async(self, *, folder, filename_prefix, **_):
        self.folders.append(folder)
        # Earth Engine writes into an existing folder with that name, else a new root one.
        target = next(
            (
                i["id"]
                for i in self.drive.items.values()
                if i["mimeType"] == FOLDER and i["name"] == folder
            ),
            None,
        ) or self.drive.add(folder, "root", FOLDER)
        if self.state == "COMPLETED":
            self.drive.add(f"{filename_prefix}.tif", target)
        return {"id": "ee-task"}

    async def get_task_async(self, task_id):
        return {"state": self.state}


@pytest.fixture
def written(monkeypatch):
    monkeypatch.setattr(export_engine, "_download_drive_item_bytes", lambda drive, item_id: b"x")
    return []


def _sepal_client(written, results_path="module_results/demo"):
    return SimpleNamespace(
        results_path=results_path,
        BASE_REMOTE_PATH="/home/sepal-user",
        files=SimpleNamespace(
            mkdir=lambda path, parents: path,
            write=lambda path, payload, overwrite: written.append(path),
        ),
    )


def _export(drive, gee, written, *, sepal_client=None, **kwargs):
    request = ExportRequest(
        ee_object=object(),
        export_kind="image",
        target="sepal",
        name="demo",
        poll_interval_seconds=0,
        **kwargs,
    )
    return asyncio.run(
        submit_export_request(
            request,
            gee_interface=gee,
            drive_interface=drive,
            sepal_client=sepal_client or _sepal_client(written),
        )
    )


@pytest.mark.parametrize("cleanup", [True, False])
def test_workspace_export_stages_in_its_own_drive_folder(written, cleanup):
    drive = _FakeDrive()
    unrelated = drive.add("demo.tif", "root")
    gee = _FakeGee(drive)

    result = _export(drive, gee, written, drive_folder="ignored", cleanup_drive_after_sepal=cleanup)

    assert re.fullmatch(r"demo_\d{4}-\d\d-\d\d_\d\d:\d\d:\d\d\.\d+", gee.folders[0])
    assert result.drive_folder == f"SEPAL/exports/{gee.folders[0]}"
    assert written == ["/home/sepal-user/module_results/demo/demo.tif"]
    assert unrelated in drive.items
    staged = [drive.path_of(i) for i in drive.items if drive.items[i]["mimeType"] != FOLDER]
    expected = ["demo.tif", f"{result.drive_folder}/demo.tif"] if not cleanup else ["demo.tif"]
    assert sorted(staged) == sorted(expected)


def test_workspace_exports_share_the_staging_parents(written):
    drive = _FakeDrive()
    sepal = drive.add("SEPAL", "root", FOLDER)

    for _ in range(2):
        _export(drive, _FakeGee(drive), written, cleanup_drive_after_sepal=False)

    assert [i["name"] for i in drive.children("root")] == ["SEPAL"]
    assert [i["name"] for i in drive.children(sepal)] == ["exports"]
    exports = drive.children(sepal)[0]["id"]
    assert len(drive.children(exports)) == 2


def test_failed_workspace_export_removes_its_staging_folder(written):
    drive = _FakeDrive()

    with pytest.raises(RuntimeError, match="FAILED"):
        _export(drive, _FakeGee(drive, state="FAILED"), written)

    exports = next(i["id"] for i in drive.items.values() if i["name"] == "exports")
    assert drive.children(exports) == []


def test_timed_out_workspace_export_keeps_its_staging_folder(written):
    drive = _FakeDrive()
    gee = _FakeGee(drive, state="RUNNING")

    with pytest.raises(TimeoutError):
        _export(drive, gee, written, timeout_seconds=0)

    # Earth Engine may still write there; removing it would scatter output in the root.
    assert any(i["name"] == gee.folders[0] for i in drive.items.values())


class _RejectingGee(_FakeGee):
    def __init__(self, drive, error):
        super().__init__(drive)
        self.error = error

    async def export_image_to_drive_async(self, *, folder, **_):
        self.folders.append(folder)
        raise self.error


@pytest.mark.parametrize(
    ("error", "kept"),
    [
        (ValueError("bad region"), False),
        (EERestException({"code": 400, "message": "Invalid argument"}), False),
        (EERestException({"code": 503, "message": "Unavailable"}), True),
        # ee-client retries these, so an earlier attempt may have created the task.
        (EERestException({"code": 429, "message": "Rate limited"}), True),
        (EERestException({"code": 401, "message": "Unauthorized"}), True),
        (httpx.ReadTimeout("read timed out"), True),
    ],
)
def test_failed_submission_keeps_staging_only_when_outcome_is_unknown(written, error, kept):
    drive = _FakeDrive()
    gee = _RejectingGee(drive, error)

    with pytest.raises(type(error)):
        _export(drive, gee, written)

    assert any(i["name"] == gee.folders[0] for i in drive.items.values()) is kept


def test_rejected_submission_removes_its_staging_folder_without_cleanup(written):
    drive = _FakeDrive()
    gee = _RejectingGee(drive, EERestException({"code": 400, "message": "Invalid argument"}))

    with pytest.raises(EERestException):
        _export(drive, gee, written, cleanup_drive_after_sepal=False)

    # No task exists, so nothing will ever be written to keep.
    assert not any(i["name"] == gee.folders[0] for i in drive.items.values())


class _CancellingGee(_FakeGee):
    """A task that shows CANCEL_REQUESTED before it reaches CANCELLED."""

    def __init__(self, drive):
        super().__init__(drive, state="RUNNING")
        self.states = iter(["CANCEL_REQUESTED", "CANCEL_REQUESTED", "CANCELLED"])
        self.seen = []

    async def get_task_async(self, task_id):
        self.seen.append(next(self.states))
        return {"state": self.seen[-1]}


def test_staging_folder_stays_until_a_cancel_requested_task_is_final(written):
    drive = _FakeDrive()
    gee = _CancellingGee(drive)

    with pytest.raises(RuntimeError, match="CANCELLED"):
        _export(drive, gee, written)

    assert gee.seen == ["CANCEL_REQUESTED", "CANCEL_REQUESTED", "CANCELLED"]
    assert not any(i["name"] == gee.folders[0] for i in drive.items.values())


@pytest.mark.parametrize(
    ("folder", "results_path"),
    [("../escape", "module_results/demo"), (None, None)],
)
def test_bad_workspace_destination_fails_before_any_remote_work(written, folder, results_path):
    drive = _FakeDrive()
    gee = _FakeGee(drive)

    with pytest.raises(ValueError):
        _export(
            drive,
            gee,
            written,
            sepal_folder=folder,
            sepal_client=_sepal_client(written, results_path=results_path),
        )

    assert gee.folders == []
    assert drive.items == {}


class _RenamingGee(_FakeGee):
    async def export_image_to_drive_async(self, *, folder, filename_prefix, **kwargs):
        await super().export_image_to_drive_async(
            folder=folder, filename_prefix=f"renamed-{filename_prefix}", **kwargs
        )
        return {"id": "ee-task"}


def test_every_file_in_the_staging_folder_is_copied(written):
    drive = _FakeDrive()

    _export(drive, _RenamingGee(drive), written, timeout_seconds=1)

    assert written == ["/home/sepal-user/module_results/demo/renamed-demo.tif"]


def test_a_hung_drive_call_does_not_block_other_users(written):
    entered, release = threading.Event(), threading.Event()
    slow, fast = _FakeDrive(user="slow-user"), _FakeDrive(user="fast-user")
    slow_list = slow.list

    def hung_list(q, **kwargs):
        entered.set()
        release.wait(5)
        return slow_list(q, **kwargs)

    slow.list = hung_list
    stuck = threading.Thread(target=_export, args=(slow, _FakeGee(slow), []))
    other = threading.Thread(target=_export, args=(fast, _FakeGee(fast), written))
    stuck.start()
    try:
        assert entered.wait(2)
        other.start()
        other.join(2)
        assert not other.is_alive()
    finally:
        release.set()
        stuck.join()
        if other.is_alive() or other.ident is not None:
            other.join()

    assert written == ["/home/sepal-user/module_results/demo/demo.tif"]

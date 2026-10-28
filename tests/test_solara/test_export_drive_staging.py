"""Direct workspace exports stage in a dedicated Drive folder, like SEPAL."""

import asyncio
import re
from types import SimpleNamespace

import pytest

from pysepal.solara.components import export_engine
from pysepal.solara.components.export_engine import submit_export_request
from pysepal.solara.components.export_models import ExportRequest

FOLDER = "application/vnd.google-apps.folder"


def _call(fn):
    return SimpleNamespace(execute=fn)


class _FakeDrive:
    """The Drive v3 ``files()`` calls the engine makes, over an in-memory tree."""

    def __init__(self):
        self.items = {}
        self.service = self

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


def _sepal_client(written):
    return SimpleNamespace(
        results_path="module_results/demo",
        BASE_REMOTE_PATH="/home/sepal-user",
        files=SimpleNamespace(
            mkdir=lambda path, parents: path,
            write=lambda path, payload, overwrite: written.append(path),
        ),
    )


def _export(drive, gee, written, **kwargs):
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
            sepal_client=_sepal_client(written),
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

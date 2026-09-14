"""``setup_solara_server`` merges the assets once per process."""

import atexit
import os
from pathlib import Path

import pytest
import solara.server.settings

import pysepal.scripts.scratch as scratch
import pysepal.solara.setup as setup


@pytest.fixture
def scratch_root(monkeypatch, tmp_path):
    """Start with no merged folder and create scratch folders under ``tmp_path``."""
    setup._remove_merged_assets()
    monkeypatch.setattr(scratch, "scratch_root", lambda: tmp_path)
    monkeypatch.setattr(atexit, "register", lambda fn: fn)
    monkeypatch.setattr(solara.server.settings.assets, "extra_locations", [])
    yield tmp_path
    setup._remove_merged_assets()


def merged_folders(root: Path) -> list:
    return sorted(root.glob("sepal_ui_assets_*"))


def merged_css() -> Path:
    (location,) = solara.server.settings.assets.extra_locations
    return Path(location) / "custom.css"


def write_extra(root: Path, rule: str) -> Path:
    extra = root / "extra"
    extra.mkdir(exist_ok=True)
    (extra / "app.css").write_text(rule)
    return extra


def test_a_second_call_reuses_the_merged_folder(scratch_root):
    setup.setup_solara_server(extra_asset_locations=[])
    first = list(solara.server.settings.assets.extra_locations)

    setup.setup_solara_server(extra_asset_locations=[])
    setup.setup_solara_server()

    assert solara.server.settings.assets.extra_locations == first
    assert len(merged_folders(scratch_root)) == 1


def test_a_later_call_adds_new_locations_to_the_same_folder(scratch_root):
    extra = write_extra(scratch_root, ".app-marker { color: red; }")
    setup.setup_solara_server(extra_asset_locations=[])
    assert ".app-marker" not in merged_css().read_text()

    setup.setup_solara_server(extra_asset_locations=[extra])

    assert ".app-marker" in merged_css().read_text()
    assert len(merged_folders(scratch_root)) == 1


def test_unchanged_inputs_do_not_merge_again(scratch_root, monkeypatch):
    extra = write_extra(scratch_root, ".app-marker {}")
    setup.setup_solara_server(extra_asset_locations=[extra])
    merges = []
    monkeypatch.setattr(setup, "merge_asset_files", lambda *args, **kwargs: merges.append(args))

    setup.setup_solara_server(extra_asset_locations=[extra])
    setup.setup_solara_server(extra_asset_locations=[str(extra)])

    assert merges == []


def test_a_changed_source_file_is_merged_again(scratch_root):
    extra = write_extra(scratch_root, ".app-marker { color: red; }")
    setup.setup_solara_server(extra_asset_locations=[extra])
    later = merged_css().stat().st_mtime_ns + 10**9
    (extra / "app.css").write_text(".app-marker { color: blue; }")
    os.utime(extra / "app.css", ns=(later, later))

    setup.setup_solara_server(extra_asset_locations=[extra])

    assert "blue" in merged_css().read_text()
    assert len(merged_folders(scratch_root)) == 1


def test_the_merged_folder_is_removed_at_exit(scratch_root, monkeypatch):
    registered = []
    monkeypatch.setattr(atexit, "register", lambda fn: registered.append(fn) or fn)

    setup.setup_solara_server()
    (folder,) = merged_folders(scratch_root)
    (cleanup,) = registered
    cleanup()

    assert not folder.exists()

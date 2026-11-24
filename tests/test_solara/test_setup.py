"""``setup_solara_server`` merges the assets once per process."""

import atexit
import hashlib
import importlib.resources
import json
import os
from pathlib import Path

import pytest
import solara.server.settings
import solara.util
from pysepal_map import MapWidget

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


def test_a_dropped_page_gets_time_to_reconnect(scratch_root, monkeypatch):
    # With "0s" a dropped websocket shuts the kernel down before the page can
    # reconnect; a closed page is freed by Solara's close beacon instead.
    monkeypatch.setattr(solara.server.settings.kernel, "cull_timeout", "24h")
    setup.setup_solara_server()

    timeout = solara.util.parse_timedelta(solara.server.settings.kernel.cull_timeout)
    assert timeout == 300


@pytest.fixture
def map_bundle(scratch_root, monkeypatch):
    """Restore the map class's inline bundle after the test, with hot reload off."""
    monkeypatch.delenv("ANYWIDGET_HMR", raising=False)
    monkeypatch.setattr(MapWidget, "_esm", MapWidget._esm)
    monkeypatch.setattr(MapWidget, "_css", MapWidget._css)
    return monkeypatch


def serving(monkeypatch, value: bool):
    monkeypatch.setattr(setup, "is_serving_connections", lambda: value)


def comm_open_bytes(widget) -> int:
    return len(json.dumps(widget.get_state()))


def test_under_a_solara_server_no_map_sends_the_bundle(map_bundle):
    serving(map_bundle, True)
    setup.setup_solara_server()

    maps = [MapWidget(), MapWidget()]
    try:
        assert [comm_open_bytes(widget) < 50_000 for widget in maps] == [True, True]
    finally:
        for widget in maps:
            widget.close()


def test_the_page_loads_the_served_bundle_by_its_hash(map_bundle):
    serving(map_bundle, True)
    static = importlib.resources.files("pysepal_map").joinpath("static")
    setup.setup_solara_server()

    served = merged_css().parent / setup.MAP_BUNDLE_FOLDER
    for name in ("widget.js", "widget.css"):
        content = (served / name).read_bytes()
        assert content == static.joinpath(name).read_bytes()
        assert f"{name}?v={hashlib.md5(content).hexdigest()[:12]}" in MapWidget._esm
    assert MapWidget._css == ""


def test_a_later_call_serves_the_bundle_again(map_bundle):
    serving(map_bundle, True)
    setup.setup_solara_server()
    loader = MapWidget._esm
    setup._remove_merged_assets()

    setup.setup_solara_server()

    assert (merged_css().parent / setup.MAP_BUNDLE_FOLDER / "widget.js").is_file()
    assert MapWidget._esm == loader


@pytest.mark.parametrize(
    "solara_server, hot_reload",
    [(False, False), (True, True)],
    ids=["voila-or-jupyter", "hot-reload"],
)
def test_voila_jupyter_and_hot_reload_keep_the_inline_bundle(map_bundle, solara_server, hot_reload):
    serving(map_bundle, solara_server)
    if hot_reload:
        map_bundle.setenv("ANYWIDGET_HMR", "1")
    inline = (MapWidget._esm, MapWidget._css)

    setup.setup_solara_server()

    assert (MapWidget._esm, MapWidget._css) == inline
    assert not (merged_css().parent / setup.MAP_BUNDLE_FOLDER).exists()

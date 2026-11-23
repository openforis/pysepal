"""Every demo app renders on the current map API, with no Earth Engine and no network.

Nothing else imports the apps, so a demo that an API change broke would only show
when someone opened it. Each test loads an app the way ``gallery.py`` does, renders
it on a live loop, and runs its buttons that move the map without Earth Engine.
"""

import ast
import asyncio
import importlib.util
import sys
from pathlib import Path

import ipyvuetify as v
import pytest
import reacton
import solara.lifecycle
import solara.server.settings

import pysepal
import pysepal.scripts.utils as su
from pysepal.i18n import set_locale
from pysepal.mapping import SepalMap
from pysepal.solara.session_manager import SessionManager
from pysepal.solara.theme import _theme_store
from tests.test_solara._layer_panel_helpers import _attr, _tree

DEMO_ROOT = Path(pysepal.__file__).parents[1] / "demo_apps"

#: The component each test renders: ``Page``, unless it opens a SEPAL session, in
#: which case the one ``ui.ipynb`` displays.
APPS = {
    "solara_aoi_app": "Page",
    "solara_aoi_gee_app": "AoiGeeAppDemo",
    "solara_chart_app": "Page",
    "solara_map_app": "MapAppDemo",
    "solara_raster_app": "Page",
    "solara_vector_app": "Page",
}


class _FakeGee:
    """An Earth Engine interface with an empty asset folder."""

    async def get_folder_async(self):
        return "users/smoke"

    async def get_assets_async(self, folder):
        return []

    async def get_asset_async(self, asset_id):
        return {"type": "IMAGE"}


class _FakeVectorLayer:
    """What the vector demo reads off the layer ``vectortileserver`` returns."""

    url = "http://127.0.0.1:9/pmtiles?filePath=/smoke/landcover.pmtiles"
    bounds = [[-0.4, 20.0], [0.0, 20.4]]  # [[south, west], [north, east]]
    name = ""

    def list_layers(self):
        return ["landcover"]


class _FakeWorkspace:
    """A ``TileWorkspace`` that converts nothing and starts no server."""

    def __init__(self, **kwargs):
        pass

    async def open_async(self, source, **kwargs):
        return _FakeVectorLayer()


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Keep what loading and rendering an app sets process-wide from leaking."""
    monkeypatch.setattr(SessionManager, "get_gee_interface", lambda self: _FakeGee())
    monkeypatch.setattr(SessionManager, "get_drive_interface", lambda self: object())
    monkeypatch.setattr(SessionManager, "get_sepal_client", lambda self, **kwargs: None)
    monkeypatch.setattr(su, "init_ee", lambda: None)
    for name in ("PYSEPAL_DEMO_RASTER_DIR", "PYSEPAL_DEMO_VECTOR_DIR"):
        monkeypatch.delenv(name, raising=False)

    settings = solara.server.settings
    monkeypatch.setattr(settings.assets, "fontawesome_path", settings.assets.fontawesome_path)
    monkeypatch.setattr(settings.assets, "extra_locations", list(settings.assets.extra_locations))
    monkeypatch.setattr(settings.kernel, "cull_timeout", settings.kernel.cull_timeout)
    callbacks = list(solara.lifecycle._on_kernel_start_callbacks)
    modules = set(sys.modules)

    SessionManager._instance = None
    _theme_store.clear()
    set_locale("en")
    yield tmp_path
    SessionManager._instance = None
    _theme_store.clear()
    set_locale("en")

    for entry in [e for e in solara.lifecycle._on_kernel_start_callbacks if e not in callbacks]:
        entry.cleanup()
    for name in set(sys.modules) - modules:
        path = getattr(sys.modules[name], "__file__", None) or ""
        if Path(path).is_relative_to(DEMO_ROOT):
            del sys.modules[name]


def _load(name: str, monkeypatch, scratch: Path):
    """Import ``<name>/app.py`` under ``name``, as ``gallery.load_demo`` does."""
    directory = DEMO_ROOT / name
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(name, directory / "app.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)

    if hasattr(module, "scratch_root"):
        monkeypatch.setattr(module, "scratch_root", lambda: scratch)
    if hasattr(module, "SAVED_AOI"):
        monkeypatch.setattr(module, "SAVED_AOI", scratch / "saved_aoi.json")
    if hasattr(module, "TileWorkspace"):
        monkeypatch.setattr(module, "TileWorkspace", _FakeWorkspace)
    return module


async def _eventually(predicate, timeout: float = 10.0) -> bool:
    """Whether ``predicate`` holds within ``timeout``, keeping the loop running meanwhile."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate() and loop.time() < deadline:
        await asyncio.sleep(0.01)
    return predicate()


def _maps(root) -> list:
    return [w for w in _tree(root) if isinstance(w, SepalMap)]


def _button(root, label: str):
    """The button showing ``label``."""
    found = [w for w in _tree(root) if isinstance(w, v.Btn) and label in (w.children or ())]
    assert len(found) == 1, f"{len(found)} buttons labelled {label!r}"
    return found[0]


def _click(root, label: str) -> None:
    _button(root, label).fire_event("click", {})


async def _aoi_app(root, module) -> None:
    pass


async def _map_app(root, module) -> None:
    (m,) = _maps(root)
    msg = module.msg
    store = m.layer_store
    assert len(store) == 2, "the map opens on the sample raster and vector"

    _click(root, msg("buttons.add_pmtiles"))
    assert "demo_pmtiles" in store
    # (lng, lat) over Christchurch
    assert m.view_request.get("center") == pytest.approx([172.6062, -43.5565])

    _click(root, msg("buttons.remove_all"))
    assert len(store) == 0


async def _chart_app(root, module) -> None:
    _click(root, module.msg("buttons.open_map"))
    assert await _eventually(lambda: len(_maps(root)) == 1)
    corner = next(w for w in _tree(root) if _attr(w, "data-corner") == "top-right")
    assert [w for w in _tree(corner) if isinstance(w, v.Menu)], "the chart menu sits top right"


async def _raster_app(root, module) -> None:
    (m,) = _maps(root)
    msg = module.msg
    _click(root, msg("buttons.continuous"))
    assert await _eventually(lambda: "continuous" in m.layer_store)

    _click(root, msg("buttons.clear_rasters"))
    assert "continuous" not in m.layer_store


async def _vector_app(root, module) -> None:
    (m,) = _maps(root)
    msg = module.msg
    store = m.layer_store

    _click(root, msg("buttons.single"))
    assert await _eventually(lambda: "single" in store)
    source = store.get("single").source
    assert (source.uri, source.format, source.layer) == (
        _FakeVectorLayer.url,
        "PMTiles",
        "landcover",
    )
    assert m.view_request["bounds"] == [20.0, -0.4, 20.4, 0.0]

    _click(root, msg("buttons.categorized"))
    assert await _eventually(lambda: "categorized" in store)
    style = store.get("categorized").style
    assert style.color_by == module.LANDCOVER_FIELD
    assert list(style.class_colors) == module.LANDCOVER_CLASSES

    _click(root, msg("buttons.clear_vectors"))
    assert "single" not in store and "categorized" not in store


EXERCISES = {
    "solara_aoi_app": _aoi_app,
    "solara_aoi_gee_app": _aoi_app,
    "solara_chart_app": _chart_app,
    "solara_map_app": _map_app,
    "solara_raster_app": _raster_app,
    "solara_vector_app": _vector_app,
}


def test_every_demo_has_a_smoke_test():
    folders = sorted(path.parent.name for path in DEMO_ROOT.glob("*/app.py"))
    assert folders == sorted(APPS) == sorted(EXERCISES)


def test_the_gallery_lists_every_demo():
    tree = ast.parse((DEMO_ROOT / "gallery.py").read_text())
    demos = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DEMOS"
    )
    listed = [ast.literal_eval(entry)[0] for entry in demos.elts]
    assert sorted(listed) == sorted(APPS)


@pytest.mark.parametrize("name", sorted(APPS))
def test_the_demo_renders_on_the_map(name, isolated, monkeypatch):
    module = _load(name, monkeypatch, isolated)
    component = getattr(module, APPS[name])

    async def run():
        root, rc = reacton.render(component(), handle_error=False)
        try:
            if name != "solara_chart_app":  # its map opens from the page
                assert len(_maps(root)) == 1
            await EXERCISES[name](root, module)
            # MapView draws the map's legend; one the app mounts itself would overlap it.
            legends = [w for w in _tree(root) if hasattr(w, "selector_options")]
            assert [w.placement for w in legends if w.placement != "map"] == []
        finally:
            rc.close()

    asyncio.run(run())

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
    "solara_compare_app": "Page",
    "solara_linked_maps_app": "Page",
    "solara_map_app": "MapAppDemo",
    "solara_raster_app": "Page",
    "solara_vector_app": "Page",
}

#: The module of the demos extra an app imports; ``nox -s test`` has neither.
NEEDS = {"solara_chart_app": "ipecharts", "solara_vector_app": "vectortileserver"}

LOOPBACK_ARCHIVE = "http://127.0.0.1:9/pmtiles?filePath=/smoke/landcover.pmtiles"


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

    bounds = [[-0.4, 20.0], [0.0, 20.4]]  # [[south, west], [north, east]]

    def __init__(self, url: str):
        self.url = url

    def list_layers(self):
        return ["landcover"]


class _FakeWorkspace:
    """A ``TileWorkspace`` that converts nothing and starts no server.

    It builds the archive's URL as ``vectortileserver`` does: the loopback URL, or the
    client prefix with the port in it.
    """

    def __init__(self, *, client_prefix=None, **kwargs):
        self.client_prefix = client_prefix

    async def open_async(self, source, **kwargs):
        base = "http://127.0.0.1:9"
        if self.client_prefix:
            base = "/" + self.client_prefix.replace("{port}", "9").strip("/")
        return _FakeVectorLayer(f"{base}/pmtiles?filePath=/smoke/landcover.pmtiles")


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Keep what loading and rendering an app sets process-wide from leaking."""
    monkeypatch.setattr(SessionManager, "get_gee_interface", lambda self: _FakeGee())
    monkeypatch.setattr(SessionManager, "get_drive_interface", lambda self: object())
    monkeypatch.setattr(SessionManager, "get_sepal_client", lambda self, **kwargs: None)
    monkeypatch.setattr(su, "init_ee", lambda: None)
    for name in (
        "PYSEPAL_DEMO_RASTER_DIR",
        "PYSEPAL_DEMO_VECTOR_DIR",
        "LOCALTILESERVER_CLIENT_PREFIX",
        "VECTORTILESERVER_CLIENT_PREFIX",
    ):
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


async def _vector_app(root, module, url: str = LOOPBACK_ARCHIVE) -> None:
    (m,) = _maps(root)
    msg = module.msg
    store = m.layer_store

    _click(root, msg("buttons.single"))
    assert await _eventually(lambda: "single" in store)
    source = store.get("single").source
    assert (source.uri, source.format, source.layer) == (url, "PMTiles", "landcover")
    # the engine took it as a URL for the browser, not as a local file it refuses
    assert await _eventually(lambda: m.layer_engine.accepted("single") is not None)
    assert m.view_request["bounds"] == [20.0, -0.4, 20.4, 0.0]

    _click(root, msg("buttons.categorized"))
    assert await _eventually(lambda: "categorized" in store)
    style = store.get("categorized").style
    assert style.color_by == module.LANDCOVER_FIELD
    assert list(style.class_colors) == module.LANDCOVER_CLASSES

    _click(root, msg("buttons.clear_vectors"))
    assert "single" not in store and "categorized" not in store


async def _compare_app(root, module) -> None:
    (m,) = _maps(root)
    store = m.layer_store
    assert m.compare
    assert await _eventually(lambda: "forest_2020" in store and "forest_2024" in store)
    assert (store.view("forest_2020").side, store.view("forest_2024").side) == ("left", "right")
    assert store.view("alerts").side == "right" and store.view("plots").side == "both"

    msg = module.msg
    _click(root, msg("draw.start"))
    assert m.draw.modes[: len(module.DRAW_MODES)] == module.DRAW_MODES
    _click(root, msg("draw.end"))
    assert m.draw.modes == ()


async def _linked_maps_app(root, module) -> None:
    maps = _maps(root)
    assert [m.link_group for m in maps] == [module.GROUP, module.GROUP, None]

    _click(root, module.msg("buttons.center"))
    assert maps[1].view_request.get("center") == pytest.approx([0, 0])

    _click(root, module.msg("buttons.fit"))
    assert await _eventually(lambda: "bounds" in maps[0].view_request)


EXERCISES = {
    "solara_aoi_app": _aoi_app,
    "solara_aoi_gee_app": _aoi_app,
    "solara_chart_app": _chart_app,
    "solara_compare_app": _compare_app,
    "solara_linked_maps_app": _linked_maps_app,
    "solara_map_app": _map_app,
    "solara_raster_app": _raster_app,
    "solara_vector_app": _vector_app,
}

#: How many maps a demo shows when it opens; the chart demo opens its map from the page.
MAP_COUNTS = {"solara_chart_app": 0, "solara_linked_maps_app": 3}


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


def _run(name: str, module, exercise) -> None:
    """Render the app's component on a live loop, run ``exercise``, then check its legends."""

    async def run():
        root, rc = reacton.render(getattr(module, APPS[name])(), handle_error=False)
        try:
            assert len(_maps(root)) == MAP_COUNTS.get(name, 1)
            await exercise(root, module)
            # MapView draws the map's legend; one the app mounts itself would overlap it.
            legends = [w for w in _tree(root) if hasattr(w, "selector_options")]
            assert [w.placement for w in legends if w.placement != "map"] == []
        finally:
            rc.close()

    asyncio.run(run())


@pytest.mark.parametrize("name", sorted(APPS))
def test_the_demo_renders_on_the_map(name, isolated, monkeypatch):
    if name in NEEDS:
        pytest.importorskip(NEEDS[name], reason="needs the demos extra: nox -s demos")
    _run(name, _load(name, monkeypatch, isolated), EXERCISES[name])


def test_the_vector_demo_draws_behind_sepals_proxy(isolated, monkeypatch):
    """SEPAL sets only the raster prefix; the demo borrows it, so the archive's URL is root-relative."""
    pytest.importorskip("vectortileserver", reason="needs the demos extra: nox -s demos")
    monkeypatch.setenv("LOCALTILESERVER_CLIENT_PREFIX", "/api/sandbox/jupyter/proxy/{port}")
    module = _load("solara_vector_app", monkeypatch, isolated)
    url = "/api/sandbox/jupyter/proxy/9/pmtiles?filePath=/smoke/landcover.pmtiles"

    async def exercise(root, module):
        await _vector_app(root, module, url)

    _run("solara_vector_app", module, exercise)

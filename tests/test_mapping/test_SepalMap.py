"""Test the SepalMap object."""

import asyncio
import math
import random
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import ee
import geopandas as gpd
import ipyvuetify as v
import pytest
import traitlets
from pysepal_map import MapWidget
from shapely.geometry import box

import pysepal.mapping.sepal_map as sepal_map_module
from pysepal.frontend import styles as ss
from pysepal.layers import GeeSource, LayerSpec, LayerStore, RenderLayer, VectorStyle
from pysepal.mapping import LayerHandle
from pysepal.mapping.basemaps import BASEMAP_NAMES, get_basemap, tile_urls, xyz_tiles
from pysepal.mapping.maplibre_engine import MapLibreEngine
from pysepal.mapping.sepal_map import SepalMap
from pysepal.mapping.visualization import get_viz_params
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara.theme import ThemeState
from tests.test_solara._harness import wait_until

# create a seed so that we can check values
random.seed(42)

TILES = "https://tiles.test/{}/{{z}}/{{x}}/{{y}}.png"


def layer_of(m: SepalMap, layer_id: str) -> Optional[dict]:
    """The published state of one layer."""
    return next((x for x in m.state.get("layers", ()) if x["id"] == layer_id), None)


def ids_of(m: SepalMap) -> list:
    return [x["id"] for x in m.state.get("layers", ())]


def msg(m: SepalMap, **content) -> None:
    """Send a message as a view would."""
    m._handle_custom_msg(content, [])


def drawn_tiles(m: SepalMap, layer_id: str, bounds=None, **kw) -> LayerSpec:
    """Add a tile layer whose render, seeded in the engine, knows ``bounds``."""
    spec = LayerSpec.from_tiles(TILES.format(layer_id), name=layer_id, id=layer_id, **kw)
    m.layer_engine.put(
        RenderLayer(
            render_hash=spec.render_hash, kind="raster-xyz", url=spec.source.url, bounds=bounds
        )
    )
    m.layer_store.add(spec, replace=True)
    return spec


def drawn_ee(m: SepalMap, gee_spec: LayerSpec, layer_id: str) -> LayerSpec:
    """Add an Earth Engine image whose bounds are only known to Earth Engine."""
    # its own expression, so that no two layers share a render
    source = GeeSource(expr={"layer": layer_id}, kind="Image")
    spec = gee_spec.model_copy(update={"id": layer_id, "name": layer_id, "source": source})
    url = f"https://ee.test/{layer_id}/{{z}}/{{x}}/{{y}}"
    m.layer_engine.put(
        RenderLayer(
            render_hash=spec.render_hash, kind="raster-xyz", url=url, ee_object=f"ee:{layer_id}"
        )
    )
    m.layer_store.add(spec)
    return spec


class SlowGee:
    """An interface whose async bounds lookup waits for ``gate``."""

    def __init__(self, answer) -> None:
        """Keep the answer to give."""
        self.answer = answer
        self.gate = asyncio.Event()
        self.calls = 0

    def get_bounds(self, item):
        self.calls += 1
        return self.answer

    async def get_bounds_async(self, item):
        self.calls += 1
        await self.gate.wait()
        return self.answer


# -- the widget ------------------------------------------------------------------------------


def test_is_a_map_widget() -> None:
    m = SepalMap(gee=False)

    assert isinstance(m, MapWidget)
    assert isinstance(m.layer_engine, MapLibreEngine) and isinstance(m.layer_store, LayerStore)
    assert m.state["controls"] == {"zoom": True, "fullscreen": False, "scale": True}
    assert m.height == "400px"
    assert (m.view_request["center"], m.view_request["zoom"]) == ([0.0, 0.0], 3.0)

    # center is (lng, lat)
    m = SepalMap(gee=False, fullscreen=True, fullscreen_control=True, center=(10, 20), zoom=5)
    assert m.state["controls"]["fullscreen"] is True
    assert m.height == "100%"
    assert (m.view_request["center"], m.view_request["zoom"]) == ([10.0, 20.0], 5.0)


def test_an_empty_supplied_store_is_kept() -> None:
    store = LayerStore()
    assert SepalMap(gee=False, layer_store=store).layer_store is store


def test_positional_options_raise() -> None:
    # the second positional argument used to be dc, then gee: it is keyword-only now
    with pytest.raises(TypeError):
        SepalMap([], False)

    m = SepalMap(gee=False)
    # the second positional argument of remove_layer used to be base
    with pytest.raises(TypeError):
        m.remove_layer("x", True)


@pytest.mark.parametrize(
    "member",
    ["add_layer", "add_control", "layers", "viewport_inset_left", "canvas_width_px"],
)
def test_removed_members_point_at_the_guide(member) -> None:
    with pytest.raises(AttributeError, match="migrating-to-pysepal-5"):
        getattr(SepalMap(gee=False), member)


def test_set_center() -> None:
    """Check the center can be updated."""
    m = SepalMap(gee=False)

    lat = random.randint(-90, 90)
    lng = random.randint(-180, 180)
    zoom = random.randint(0, 22)
    m.set_center(lng, lat, zoom)

    assert m.view_request["center"] == [lng, lat]
    assert m.view_request["zoom"] == zoom

    m.setCenter(lng=1, lat=2)
    assert m.view_request["center"] == [1, 2]


# -- basemaps ---------------------------------------------------------------------------------


def test_default_basemap_follows_the_theme() -> None:
    for mode, name in [("light", "SEPAL_LIGHT"), ("dark", "SEPAL_DARK")]:
        m = SepalMap(gee=False, theme_state=ThemeState(mode=mode))
        assert (m.basemaps, m.basemap) == ((name,), name)
        assert m.state["basemap"]["tiles"] == list(get_basemap(name).tiles)

    # the global theme when no state is given
    name = "SEPAL_DARK" if v.theme.dark else "SEPAL_LIGHT"
    assert SepalMap(gee=False).basemaps == (name,)


def test_basemaps_keep_the_caller_order() -> None:
    # xyz_tiles keys, so that an upstream provider needing a key cannot take them out (#1044)
    m = SepalMap(["ROADMAP", "TERRAIN", "ROADMAP"], gee=False)

    assert (m.basemaps, m.basemap) == (("ROADMAP", "TERRAIN"), "ROADMAP")
    assert m.state["basemap"]["tiles"] == list(get_basemap("ROADMAP").tiles)

    with pytest.raises(ValueError):
        SepalMap(["TOTO"], gee=False)


def test_theme_switch_swaps_every_sepal_choice_and_keeps_a_third_party_pick() -> None:
    theme = ThemeState(mode="light")
    m = SepalMap(["SEPAL_LIGHT", "OpenStreetMap", "SEPAL_DARK"], gee=False, theme_state=theme)
    assert m.basemaps == ("SEPAL_LIGHT", "OpenStreetMap", "SEPAL_DARK")

    theme.set_mode("dark")
    assert (m.basemaps, m.basemap) == (("SEPAL_DARK", "OpenStreetMap"), "SEPAL_DARK")
    assert m.state["basemap"]["tiles"] == list(get_basemap("SEPAL_DARK").tiles)

    m.basemap = "OpenStreetMap"
    theme.set_mode("light")
    assert (m.basemaps, m.basemap) == (("SEPAL_LIGHT", "OpenStreetMap"), "OpenStreetMap")
    assert m.state["basemap"]["tiles"] == list(get_basemap("OpenStreetMap").tiles)


def test_basemap_observer_never_sees_an_invalid_pair() -> None:
    theme = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme)
    pairs = []
    m.observe(lambda _: pairs.append((m.basemaps, m.basemap)), names=["basemaps", "basemap"])

    m.add_basemap("HYBRID")
    theme.set_mode("dark")
    m.basemap = "SEPAL_DARK"
    m.add_basemap("OpenStreetMap")

    assert pairs and all(current in choices for choices, current in pairs)
    final = (("SEPAL_DARK", "HYBRID", "OpenStreetMap"), "OpenStreetMap")
    assert (m.basemaps, m.basemap) == final

    with pytest.raises(traitlets.TraitError):
        m.basemap = "ROADMAP"  # not among the choices
    with pytest.raises(traitlets.TraitError):
        m.basemaps = ("ROADMAP",)  # leaves the current one out
    with pytest.raises(ValueError):
        m.add_basemap("TOTO")
    assert (m.basemaps, m.basemap) == final


def test_add_basemap() -> None:
    m = SepalMap(gee=False, theme_state=ThemeState(mode="light"))
    m.add_basemap("HYBRID")

    assert (m.basemaps, m.basemap) == (("SEPAL_LIGHT", "HYBRID"), "HYBRID")
    assert m.state["basemap"]["tiles"] == list(get_basemap("HYBRID").tiles)

    # a choice already there is made current, not repeated
    m.add_basemap("SEPAL_LIGHT")
    assert (m.basemaps, m.basemap) == (("SEPAL_LIGHT", "HYBRID"), "SEPAL_LIGHT")


def test_get_basemap_list() -> None:
    """Every key SepalMap will accept as a basemap has to be listed (#1044)."""
    res = SepalMap.get_basemap_list()

    assert res == list(BASEMAP_NAMES)
    assert all(key in res for key in xyz_tiles)


# -- theme ------------------------------------------------------------------------------------


def test_map_theme_trait_follows_its_own_theme_state() -> None:
    light, dark = ThemeState(mode="light"), ThemeState(mode="dark")
    a, b = SepalMap(gee=False, theme_state=light), SepalMap(gee=False, theme_state=dark)
    seen = []
    a.observe(lambda change: seen.append(change["new"]), "theme")
    assert (a.theme, b.theme) == ("light", "dark")
    assert (a.state["theme"], b.state["theme"]) == ("light", "dark")

    light.set_mode("dark")
    assert (a.theme, a.state["theme"], seen) == ("dark", "dark", ["dark"])
    assert b.theme == "dark"

    dark.set_mode("light")
    assert (a.theme, b.theme) == ("dark", "light")

    a.bind_theme_state(ThemeState(mode="light"))
    assert (a.theme, a.state["theme"]) == ("light", "light")


def test_the_map_theme_is_read_only() -> None:
    m = SepalMap(gee=False, theme_state=ThemeState(mode="light"))
    with pytest.raises(traitlets.TraitError):
        m.theme = "dark"
    assert (m.theme, m.state["theme"]) == ("light", "light")


def _dark_observers(source):
    """Return the handlers ``source`` will call when ``dark`` changes."""
    return source._trait_notifiers.get("dark", {}).get("change", [])


def test_a_closed_map_stops_following_its_theme_state() -> None:
    theme_state = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme_state)
    m.close()

    theme_state.set_mode("dark")

    assert m.theme == "light"


def test_a_closed_map_stops_following_the_global_vuetify_theme() -> None:
    """The default source is ``v.theme``, process-global and never collected.

    A map that keeps observing it is retained for the life of the process,
    which the per-kernel theme store does not help with.
    """
    m = SepalMap(gee=False)
    m.close()

    assert not [h for h in _dark_observers(v.theme) if getattr(h, "__self__", None) is m]


def test_a_closed_map_is_not_referenced_by_its_theme_state() -> None:
    """The bound method traitlets keeps is what holds the map."""
    theme_state = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme_state)
    m.close()

    assert not [h for h in _dark_observers(theme_state) if getattr(h, "__self__", None) is m]


@pytest.fixture
def square_gdf() -> gpd.GeoDataFrame:
    """A small square around the Vatican."""
    return gpd.GeoDataFrame(geometry=[box(12.445, 41.899, 12.459, 41.909)], crs="EPSG:4326")


def test_a_vector_without_a_stroke_follows_the_map_theme(square_gdf) -> None:
    """The AOI takes the theme the map is bound to, not the process-global palette."""
    theme_state = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme_state)
    m.layer_store.add(LayerSpec.from_geojson(square_gdf, id="aoi", name="aoi", zone="overlay"))

    paint = layer_of(m, "aoi")["paint"]
    assert paint["stroke"] == paint["fill"] == ss.THEMES[False]["primary"]

    theme_state.set_mode("dark")
    paint = layer_of(m, "aoi")["paint"]
    assert paint["stroke"] == paint["fill"] == ss.THEMES[True]["primary"]


def test_a_vector_with_its_own_stroke_ignores_the_theme(square_gdf) -> None:
    theme_state = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme_state)
    style = VectorStyle(stroke="#ff0000", fill="#ff0000")
    m.layer_store.add(LayerSpec.from_geojson(square_gdf, id="aoi", name="aoi", style=style))

    theme_state.set_mode("dark")
    paint = layer_of(m, "aoi")["paint"]
    assert (paint["stroke"], paint["fill"]) == ("#ff0000", "#ff0000")


# -- layers -----------------------------------------------------------------------------------


def test_add_raster_returns_a_handle_drawn_in_state(rgb: Path) -> None:
    m = SepalMap(gee=False)

    h = m.add_raster(rgb, layer_name="rgb")

    assert isinstance(h, LayerHandle) and (h.id, h.name) == ("rgb", "rgb")
    _, render = m.layer_engine.accepted("rgb")
    layer = layer_of(m, "rgb")
    assert layer["kind"] == "raster" and layer["zone"] == "data"
    assert layer["source"]["tiles"] == list(tile_urls(render.url))
    assert m.find_layer("rgb") == h


def test_add_raster(rgb: Path, byte: Path) -> None:
    """Add raster files to the map."""
    m = SepalMap(gee=False)

    m.add_raster(rgb, layer_name="rgb")
    m.add_raster(byte, layer_name="byte")

    assert m.layer_store.ids == ["byte", "rgb"]
    assert ids_of(m) == ["byte", "rgb"]
    assert m.find_layer("byte").name == "byte"


def test_find_layer_uses_drawing_order() -> None:
    m = SepalMap(gee=False)
    store = m.layer_store
    store.add(LayerSpec.from_tiles(TILES.format("o"), name="x", id="o", zone="overlay"))
    store.add(LayerSpec.from_tiles(TILES.format("d"), name="x", id="d"))
    store.add(LayerSpec.from_tiles(TILES.format("z"), name="d", id="z"))
    assert store.ids == ["z", "d", "o"]

    # a name: the first in drawing order, the overlay zone before the data zone
    assert m.find_layer("x") == LayerHandle(m, "o")
    # an id beats a name
    assert m.find_layer("d") == LayerHandle(m, "d")
    assert m.find_layer(LayerHandle(m, "z")) == LayerHandle(m, "z")
    assert m.find_layer("nothing") is None


def test_remove_layer_rejects_a_handle_from_another_store() -> None:
    a, b = SepalMap(gee=False), SepalMap(gee=False)
    a.layer_store.add(LayerSpec.from_tiles(TILES.format("t"), name="t", id="t"))
    h = a.find_layer("t")

    with pytest.raises(ValueError):
        b.remove_layer(h)
    with pytest.raises(ValueError):
        b.find_layer(h)
    with pytest.raises(ValueError):
        b.remove_layer("t")
    b.remove_layer("t", none_ok=True)
    assert "t" in a.layer_store

    a.remove_layer(h)
    assert "t" not in a.layer_store


def test_remove_all_covers_both_zones() -> None:
    m = SepalMap(gee=False)
    store = m.layer_store
    store.add(LayerSpec.from_tiles(TILES.format("o"), name="o", id="o", zone="overlay"))
    store.add(LayerSpec.from_tiles(TILES.format("d"), name="d", id="d"))
    store.add(LayerSpec.from_tiles(TILES.format("k"), name="kept", id="k"))
    store.reserve("p", "pending")

    m.remove_all(keep_names=["kept"])

    assert store.ids == ["k"] and store.reserved() == {}
    assert ids_of(m) == ["k"]


@pytest.mark.asyncio
async def test_overlay_goes_through_reservations(gee_spec, monkeypatch) -> None:
    gate = asyncio.Event()

    async def slow_prepare(spec, **kw):
        await gate.wait()
        url = "https://ee.test/{z}/{x}/{y}"
        return RenderLayer(render_hash=spec.render_hash, kind="raster-xyz", url=url)

    monkeypatch.setattr(sepal_map_module, "prepare", slow_prepare)
    monkeypatch.setattr(SepalMap, "_ee_spec", lambda self, *args, **kwargs: gee_spec)
    m = SepalMap(gee=False)
    m.gee_interface = None

    # remove_all during an async overlay add: nothing lands
    pending = asyncio.create_task(m.add_ee_layer_async(None, overlay=True))
    await wait_until(lambda: gee_spec.id in m.layer_store.reserved())
    m.remove_all()
    gate.set()
    assert await pending is None
    assert gee_spec.id not in m.layer_store and m.layer_store.reserved() == {}

    # without one it lands in the overlay zone
    handle = await m.add_ee_layer_async(None, overlay=True)
    m.layer_engine.flush()
    assert handle == LayerHandle(m, gee_spec.id)
    assert m.layer_store.get(gee_spec.id).zone == "overlay"
    assert layer_of(m, gee_spec.id)["zone"] == "overlay"


@pytest.mark.asyncio
async def test_closed_map_commits_no_pending_add(byte, monkeypatch) -> None:
    gates = []

    async def slow_prepare(spec, **kw):
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return sepal_map_module.prepare_sync(spec, **kw)

    monkeypatch.setattr(sepal_map_module, "prepare", slow_prepare)
    store = LayerStore()
    m = SepalMap(gee=False, layer_store=store)
    store.reserve("other", "Other")  # another writer's pending add
    pending = asyncio.create_task(m.add_raster_async(byte, key="k"))
    await wait_until(lambda: len(gates) == 1)

    m.close()
    gates[0].set()

    assert await pending is None
    assert "k" not in store and store.reserved() == {"other": "Other"}
    assert await m.add_raster_async(byte, key="late") is None
    assert "late" not in store and len(gates) == 1


# -- zoom -------------------------------------------------------------------------------------


def test_zoom_bounds_default_is_the_exact_fit() -> None:
    m = SepalMap(gee=False)
    assert m.zoom_bounds((10, 10, 20, 20)) is m
    assert m.view_request["bounds"] == [10, 10, 20, 20]
    assert m.view_request["padding"] == 20
    assert (m.view_request["zoom_out"], m.view_request["max_zoom"]) == (0, 18)

    m.zoom_bounds((10, 10, 20, 20), 5)
    assert m.view_request["zoom_out"] == 4


def test_point_fit_stops_at_18() -> None:
    m = SepalMap(gee=False)
    m.zoom_bounds((12.5, 41.9, 12.5, 41.9))
    assert m.view_request["bounds"] == [12.5, 41.9, 12.5, 41.9]
    assert m.view_request["max_zoom"] == 18


def test_zoom_raster(byte: Path) -> None:
    m = SepalMap(gee=False)
    h = m.add_raster(byte, fit_bounds=False)
    _, render = m.layer_engine.accepted(h.id)
    fit = list(render.bounds)

    assert m.zoom_raster(h) is m
    assert m.view_request["bounds"] == fit

    m.set_center(0, 0)
    m.zoom_raster(h.id)
    assert m.view_request["bounds"] == fit

    # a file is read with rioxarray
    m.set_center(0, 0)
    m.zoom_raster(byte)
    assert m.view_request["bounds"] == pytest.approx(fit, abs=0.01)


def test_zoom_layer_passes_the_engine_outcome_through(gee_spec) -> None:
    m = SepalMap(gee=False)
    drawn_tiles(m, "b", (1.0, 1.0, 2.0, 2.0))
    drawn_tiles(m, "nb")
    drawn_ee(m, gee_spec, "ee")

    assert m.zoom_layer("missing") == "missing"
    assert m.zoom_layer("nb") == "no_bounds"
    assert m.zoom_layer("ee") == "failed"  # no Earth Engine interface to ask
    assert m.zoom_layer("b") == "moved"
    assert m.view_request["bounds"] == [1.0, 1.0, 2.0, 2.0]
    assert m.find_layer("b").zoom() == "moved"


@pytest.mark.asyncio
async def test_slow_zoom_is_superseded_by_a_newer_one(gee_spec) -> None:
    m = SepalMap(gee=False)
    gee = SlowGee((10.0, 10.0, 20.0, 20.0))
    m.layer_engine.gee_interface = gee
    drawn_ee(m, gee_spec, "a")
    drawn_tiles(m, "b", (1.0, 1.0, 2.0, 2.0))

    slow = asyncio.create_task(m.zoom_layer_async("a"))
    await wait_until(lambda: gee.calls == 1)
    assert await m.zoom_layer_async("b") == "moved"
    gee.gate.set()

    assert await slow == "superseded"
    assert m.view_request["bounds"] == [1.0, 1.0, 2.0, 2.0]


class GatedGee:
    """Answers each async bounds lookup when its own gate opens."""

    def __init__(self) -> None:
        """Start with no lookup."""
        self.gates: dict = {}

    async def get_bounds_async(self, item):
        gate = self.gates[item] = asyncio.Event()
        await gate.wait()
        west = float(item.removeprefix("ee:a"))
        return (west, 0.0, west + 1, 1.0)


@pytest.mark.asyncio
async def test_an_older_zoom_answering_first_is_superseded(gee_spec) -> None:
    """Two slow zooms: the first click's answer comes first, the second click wins."""
    m = SepalMap(gee=False)
    gee = GatedGee()
    m.layer_engine.gee_interface = gee
    drawn_ee(m, gee_spec, "a1")
    drawn_ee(m, gee_spec, "a2")

    first = asyncio.create_task(m.zoom_layer_async("a1"))
    second = asyncio.create_task(m.zoom_layer_async("a2"))
    await wait_until(lambda: len(gee.gates) == 2)
    gee.gates["ee:a1"].set()
    assert await first == "superseded"
    gee.gates["ee:a2"].set()

    assert await second == "moved"
    assert m.view_request["bounds"] == [2.0, 0.0, 3.0, 1.0]


@pytest.mark.asyncio
async def test_slow_zoom_loses_to_a_direct_fit_bounds(gee_spec) -> None:
    m = SepalMap(gee=False)
    gee = SlowGee((10.0, 10.0, 20.0, 20.0))
    m.layer_engine.gee_interface = gee
    drawn_ee(m, gee_spec, "a")

    slow = asyncio.create_task(m.zoom_layer_async("a"))
    await wait_until(lambda: gee.calls == 1)
    m.fit_bounds((1.0, 1.0, 2.0, 2.0))
    gee.gate.set()

    assert await slow == "superseded"
    assert m.view_request["bounds"] == [1.0, 1.0, 2.0, 2.0]

    # the lookup is cached, and nothing newer runs: the zoom moves
    assert await m.zoom_layer_async("a") == "moved"
    assert m.view_request["bounds"] == [10.0, 10.0, 20.0, 20.0]


@pytest.mark.asyncio
async def test_stale_no_bounds_is_superseded(gee_spec) -> None:
    m = SepalMap(gee=False)
    gee = SlowGee((-180.0, -90.0, 180.0, 90.0))  # unbounded
    m.layer_engine.gee_interface = gee
    drawn_ee(m, gee_spec, "a")
    seq = m.view_request["seq"]

    slow = asyncio.create_task(m.zoom_layer_async("a"))
    await wait_until(lambda: gee.calls == 1)
    drawn_tiles(m, "a", (1.0, 1.0, 2.0, 2.0))  # replaced under the same id
    gee.gate.set()

    assert await slow == "superseded"
    assert m.view_request["seq"] == seq
    assert await m.zoom_layer_async("a") == "moved"


@pytest.mark.asyncio
async def test_a_closed_map_supersedes_its_pending_zoom(gee_spec) -> None:
    m = SepalMap(gee=False)
    gee = SlowGee((10.0, 10.0, 20.0, 20.0))
    m.layer_engine.gee_interface = gee
    drawn_ee(m, gee_spec, "a")

    slow = asyncio.create_task(m.zoom_layer_async("a"))
    await wait_until(lambda: gee.calls == 1)
    m.close()
    gee.gate.set()

    assert await slow == "superseded"


def test_get_scale_before_and_after_a_report() -> None:
    m = SepalMap(gee=False, center=(0, 0), zoom=0)
    assert math.isclose(m.get_scale(), 78271.517)
    assert m.getScale() == m.get_scale()

    msg(m, type="view_open", view_id="v", side="main")
    msg(
        m,
        type="view_report",
        view_id="v",
        request_seq=1,
        center=[10.0, 60.0],
        zoom=2.0,
        bounds=[0.0, 50.0, 20.0, 70.0],
        cause="user",
    )
    assert math.isclose(m.get_scale(), 78271.517 * 0.5 / 4)


# -- review focus -----------------------------------------------------------------------------


def test_shared_store_two_maps(rgb) -> None:
    store = LayerStore()
    a, b = SepalMap(gee=False, layer_store=store), SepalMap(gee=False, layer_store=store)
    a.add_raster(rgb, layer_name="r")
    assert [layer["id"] for layer in b.state["layers"]] == ["r"]

    a.close()
    store.set_visible("r", False)
    assert b.state["layers"][0]["visible"] is False and "r" in store


def test_shared_store_tile_error_clears_with_its_map() -> None:
    """One map headless, the other mounted with a tile error."""
    store = LayerStore()
    quiet, shown = SepalMap(gee=False, layer_store=store), SepalMap(gee=False, layer_store=store)
    store.add(LayerSpec.from_tiles(TILES.format("t"), name="t", id="t"))
    assert store.view("t").status == "ready"

    msg(shown, type="view_open", view_id="v", side="main")
    drawn = layer_of(shown, "t")
    msg(
        shown,
        type="status",
        view_id="v",
        side="main",
        id="t",
        token=drawn["token"],
        instance=drawn["instance"],
        status="error",
        error="tile 500",
    )
    assert (store.view("t").status, store.view("t").error) == ("error", "tile 500")

    shown.close()
    assert (store.view("t").status, store.view("t").error) == ("ready", "")
    store.set_opacity("t", 0.3)
    assert layer_of(quiet, "t")["opacity"] == 0.3


# -- Earth Engine -----------------------------------------------------------------------------


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_zoom_ee_object() -> None:
    """Check we can zoom on a GEE object."""
    m = SepalMap()
    ee_object = ee.FeatureCollection("FAO/GAUL/2015/level0").filter(
        ee.Filter.eq("ADM0_NAME", "France")
    )

    m.zoom_ee_object(ee_object.geometry())
    west, south, east, north = m.view_request["bounds"]
    assert ((west + east) / 2, (south + north) / 2) == pytest.approx((2.5, 46.5), abs=5)
    assert m.view_request["zoom_out"] == 0

    m.centerObject(ee_object.geometry(), 3)
    assert m.view_request["zoom_out"] == 2


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_ee_layer_exceptions() -> None:
    """Check exceptions are raised on ee_layer method."""
    map_ = SepalMap()

    # Test add a non ee map element
    with pytest.raises(AttributeError):
        map_.addLayer({})

    # Test add a feature collection with invalid style
    geometry = ee.FeatureCollection(
        ee.Geometry.Polygon(
            [
                [
                    [-103.198046875, 36.866172202843465],
                    [-103.198046875, 34.655531078083534],
                    [-100.385546875, 34.655531078083534],
                    [-100.385546875, 36.866172202843465],
                ]
            ],
        )
    )

    with pytest.raises(TypeError):
        map_.addLayer(geometry, {"invalid_propery": "red", "fillColor": None})


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_ee_layer(image_id: str) -> None:
    """Add a GEE layer on the map."""
    image = ee.Image(image_id)
    m = SepalMap()

    # display all the viz available in the image
    for viz in get_viz_params(image, m.gee_interface).values():
        m.addLayer(image, {}, viz["name"], viz_name=viz["name"])

    assert len(m.layer_store) == 4

    # display an image without properties
    m = SepalMap()
    dataset = ee.Image("CSP/ERGo/1_0/Global/ALOS_mTPI")
    dataset = ee.Image().addBands(dataset)  # with all bands and 0 properties
    assert isinstance(m.addLayer(dataset), LayerHandle)
    assert len(m.layer_store) == 1

    # Test with vector
    geometry = ee.FeatureCollection(
        ee.Geometry.Polygon(
            [
                [
                    [-103.198046875, 36.866172202843465],
                    [-103.198046875, 34.655531078083534],
                    [-100.385546875, 34.655531078083534],
                    [-100.385546875, 36.866172202843465],
                ]
            ],
        )
    )
    map_ = SepalMap()
    map_.addLayer(geometry, {"color": "red", "fillColor": None})
    assert len(map_.layer_store) == 1


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_viz_params(image_id: str) -> None:
    """Check I identify all the viz parameter from Daniel W. asset."""
    image = ee.Image(image_id)
    with GEEInterface() as gee_interface:
        res = get_viz_params(image, gee_interface)

    expected = {
        "1": {
            "bands": ["ndwi_phase_1", "ndwi_amplitude_1", "ndwi_rmse"],
            "max": [2.40625, 3296.0, 1792.0],
            "name": "NDWI harmonics",
            "min": [-2.1875, 352.0, 320.0],
            "type": "hsv",
            "inverted": [False, False, True],
        },
        "3": {
            "labels": ["Foo", "Bar", "Baz"],
            "bands": ["class"],
            "type": "categorical",
            "name": "Classification",
            "values": [5, 200, 1000],
            "palette": ["#042333", "#b15f82", "#e8fa5b"],
        },
        "2": {
            "bands": ["ndwi"],
            "name": "NDWI",
            "min": -8450,
            "max": 6610,
            "type": "continuous",
            "palette": [
                "#042333",
                "#2c3395",
                "#744992",
                "#b15f82",
                "#eb7958",
                "#fbb43d",
                "#e8fa5b",
            ],
        },
        "0": {
            "max": 2000,
            "type": "rgb",
            "min": 0,
            "name": "RGB",
            "gamma": 1.2,
            "bands": ["red", "green", "blue"],
        },
    }

    assert res == expected


@pytest.fixture(scope="function")
def ee_map_with_layers(image_id: str) -> SepalMap:
    """A sepalMap supporting each combo band from the asset."""
    image = ee.Image(image_id)
    m = SepalMap()

    # display all the viz available in the image
    for viz in get_viz_params(image, m.gee_interface).values():
        m.addLayer(image, {}, viz["name"], viz_name=viz["name"])

    return m


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_remove_layer(ee_map_with_layers: SepalMap) -> None:
    """Remove a specific layer from the map."""
    m = ee_map_with_layers

    m.remove_layer("Classification")
    assert len(m.layer_store) == 3 and m.find_layer("Classification") is None

    m.remove_layer(m.layer_store.ids[0])
    assert len(m.layer_store) == 2


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_remove_all(ee_map_with_layers: SepalMap) -> None:
    """Remove all layers from the map."""
    m = ee_map_with_layers

    m.remove_all(keep_names=["RGB"])
    assert [spec.name for spec in m.layer_store.specs()] == ["RGB"]

    m.remove_all()
    assert len(m.layer_store) == 0


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_find_layer(ee_map_with_layers: SepalMap) -> None:
    """Find a layer in a map."""
    m = ee_map_with_layers

    # search by name
    res = m.find_layer("Classification")
    assert isinstance(res, LayerHandle) and res.name == "Classification"

    # a missing layer
    assert m.find_layer("toto") is None

    # search by key, and by handle
    assert m.find_layer(res.id) == res
    assert m.find_layer(res) == res

    # search something that is not a key
    with pytest.raises(TypeError):
        m.find_layer(m)


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_ee_layer_autocenter_sync() -> None:
    """Autocenter fits the bounds Earth Engine computes for the object."""
    m = SepalMap()
    ee_object = ee.Geometry.Rectangle([1, 2, 3, 4])

    # Mock the extent get_bounds computes for the object (per-feature-bbox, #996)
    m.gee_interface.get_bounds = MagicMock(return_value=(1, 2, 3, 4))
    m.gee_interface.get_map_id = MagicMock(
        return_value={"tile_fetcher": MagicMock(url_format="http://test/{z}/{x}/{y}")}
    )

    m.add_ee_layer(ee_object, autocenter=True, name="test_layer")

    assert m.view_request["bounds"] == [1, 2, 3, 4]


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
@pytest.mark.asyncio
async def test_add_ee_layer_autocenter_async() -> None:
    """Autocenter fits the bounds Earth Engine computes for the object."""
    m = SepalMap()
    ee_object = ee.Geometry.Rectangle([1, 2, 3, 4])

    m.gee_interface.get_bounds_async = AsyncMock(return_value=(1, 2, 3, 4))
    m.gee_interface.get_map_id_async = AsyncMock(
        return_value={"tile_fetcher": MagicMock(url_format="http://test/{z}/{x}/{y}")}
    )

    await m.add_ee_layer_async(ee_object, autocenter=True, name="test_layer")

    assert m.view_request["bounds"] == [1, 2, 3, 4]


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_ee_layer_no_autocenter_sync() -> None:
    """No camera request when autocenter=False in sync add_ee_layer."""
    m = SepalMap()
    ee_object = ee.Geometry.Rectangle([-180, -90, 180, 90])

    m.gee_interface.get_info = MagicMock(return_value=[])
    m.gee_interface.get_map_id = MagicMock(
        return_value={"tile_fetcher": MagicMock(url_format="http://test/{z}/{x}/{y}")}
    )
    seq = m.view_request["seq"]

    m.add_ee_layer(ee_object, autocenter=False, name="test_layer")

    assert m.view_request["seq"] == seq


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
@pytest.mark.asyncio
async def test_add_ee_layer_no_autocenter_async() -> None:
    """No camera request when autocenter=False in add_ee_layer_async."""
    m = SepalMap()
    ee_object = ee.Geometry.Rectangle([-180, -90, 180, 90])

    m.gee_interface.get_info_async = AsyncMock(return_value=[])
    m.gee_interface.get_map_id_async = AsyncMock(
        return_value={"tile_fetcher": MagicMock(url_format="http://test/{z}/{x}/{y}")}
    )
    seq = m.view_request["seq"]

    await m.add_ee_layer_async(ee_object, autocenter=False, name="test_layer")

    assert m.view_request["seq"] == seq


def _fake_map_id(image: ee.Image, vis_params: dict) -> dict:
    """Stand in for getMapId: the URL records the colour the tiles were styled with."""
    url = f"https://tiles.test/{vis_params.get('color')}/{{z}}/{{x}}/{{y}}"
    return {"tile_fetcher": MagicMock(url_format=url)}


def _tile_url(color: Optional[str]) -> str:
    return f"https://tiles.test/{color}/{{z}}/{{x}}/{{y}}"


def _offline_gee_map(theme_state: ThemeState) -> SepalMap:
    m = SepalMap(theme_state=theme_state)
    m.gee_interface.get_info = MagicMock(return_value=[])
    m.gee_interface.get_info_async = AsyncMock(return_value=[])
    m.gee_interface.get_map_id = MagicMock(side_effect=_fake_map_id)
    m.gee_interface.get_map_id_async = AsyncMock(side_effect=_fake_map_id)
    return m


async def _add_ee_layer(m: SepalMap, sync: bool, *args) -> None:
    if sync:
        m.add_ee_layer(*args)
    else:
        await m.add_ee_layer_async(*args)


def _drawn_url(m: SepalMap, layer_id: str) -> str:
    """The tile URL the browser gets for a layer."""
    m.layer_engine.flush()
    return layer_of(m, layer_id)["source"]["tiles"][0]


def _map_id_calls(m: SepalMap, sync: bool) -> int:
    mock = m.gee_interface.get_map_id if sync else m.gee_interface.get_map_id_async
    return mock.call_count


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
@pytest.mark.asyncio
@pytest.mark.parametrize("sync", [True, False])
async def test_an_ee_vector_in_the_default_colour_follows_the_map_theme(sync: bool) -> None:
    """Earth Engine bakes the colour into the tiles, so the layer swaps renders."""
    theme_state = ThemeState(mode="light")
    m = _offline_gee_map(theme_state)
    await _add_ee_layer(m, sync, ee.FeatureCollection(ee.Geometry.Point(0, 0)), {}, "aoi")

    assert _drawn_url(m, "aoi") == _tile_url(ss.LIGHT_THEME["primary"])

    theme_state.set_mode("dark")
    assert _drawn_url(m, "aoi") == _tile_url(ss.DARK_THEME["primary"])

    theme_state.set_mode("light")
    assert _drawn_url(m, "aoi") == _tile_url(ss.LIGHT_THEME["primary"])


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
@pytest.mark.asyncio
@pytest.mark.parametrize("sync", [True, False])
async def test_an_ee_vector_with_its_own_colour_is_rendered_once(sync: bool) -> None:
    theme_state = ThemeState(mode="light")
    m = _offline_gee_map(theme_state)
    fc = ee.FeatureCollection(ee.Geometry.Point(0, 0))
    await _add_ee_layer(m, sync, fc, {"color": "#ff0000"}, "aoi")

    theme_state.set_mode("dark")
    # the layer spec hands Earth Engine its colours as bare hex
    assert _drawn_url(m, "aoi") == _tile_url("ff0000")
    assert _map_id_calls(m, sync) == 1


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
@pytest.mark.asyncio
@pytest.mark.parametrize("sync", [True, False])
async def test_an_ee_image_is_rendered_once_without_a_colour(sync: bool) -> None:
    """``color`` is a vector style: an image given one fails to render."""
    theme_state = ThemeState(mode="light")
    m = _offline_gee_map(theme_state)
    await _add_ee_layer(m, sync, ee.Image(1), {"min": 0, "max": 1}, "image")

    theme_state.set_mode("dark")
    assert _drawn_url(m, "image") == _tile_url(None)
    assert _map_id_calls(m, sync) == 1


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_an_ee_overlay_draws_above_the_data_layers(byte) -> None:
    m = SepalMap()
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([0, 0]).buffer(1000))])
    m.add_ee_layer(fc, {}, "aoi", overlay=True)
    m.add_raster(byte, key="data")

    assert m.layer_store.ids == ["data", "aoi"]
    assert ids_of(m) == ["aoi", "data"]
    assert layer_of(m, "aoi")["zone"] == "overlay"

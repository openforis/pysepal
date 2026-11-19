"""SepalMap draws its layers through a LayerStore and a LeafletEngine."""

import asyncio

import ee
import ipyleaflet as ipl
import ipyvuetify as v
import pytest

import pysepal.mapping.sepal_map as sepal_map_module
from pysepal.frontend.styles import THEMES
from pysepal.layers import (
    LayerPrepareError,
    LayerSpec,
    LayerStore,
    RenderLayer,
    prepare_sync,
)
from pysepal.mapping.layer_engine import OVERLAY_PANE
from pysepal.mapping.sepal_map import SepalMap
from pysepal.solara.theme import ThemeState
from tests.test_solara._harness import wait_until


def test_map_owns_a_store():
    m = SepalMap(gee=False)
    assert isinstance(m.layer_store, LayerStore) and not any(
        type(c).__name__ == "LayersControl" for c in m.controls
    )


def test_prefilled_store_attaches_with_stored_visibility(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b, visible=False)
    m = SepalMap(gee=False, layer_store=store)
    a, b = m.layer_engine.leaflet_layer(raster_spec.id), m.layer_engine.leaflet_layer(
        raster_spec_b.id
    )
    # hidden = built but detached
    assert m.layer_store is store and a in m.layers and b is not None and b not in m.layers


def test_prefilled_store_takes_the_bound_theme(fake_vector):
    # the opposite of the process-wide theme, which the map follows until it binds its own
    dark = not v.theme.dark
    store = LayerStore()
    store.add(LayerSpec.from_vector(fake_vector, id="v"))
    m = SepalMap(
        gee=False, theme_state=ThemeState(mode="dark" if dark else "light"), layer_store=store
    )
    assert m.layer_engine.leaflet_layer("v").style["color"] == THEMES[dark]["primary"]


def test_map_layers_keep_the_add_order(byte):
    # each add on top re-panes the layers below it; m.layers, which an index reads, keeps the order
    m = SepalMap(gee=False)
    for key in ("a", "b", "c"):
        m.add_raster(byte, key=key)
    assert [lyr.key for lyr in m.layers if getattr(lyr, "layer_id", None)] == ["a", "b", "c"]
    assert m.find_layer(-1) is m.layer_engine.leaflet_layer("c")


def test_async_wrapper_stale_completion(byte, monkeypatch):
    gates = []

    async def slow_prepare(spec, **kw):
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return prepare_sync(spec, **kw)

    monkeypatch.setattr(sepal_map_module, "prepare", slow_prepare)

    async def run():
        m = SepalMap(gee=False)
        first = asyncio.create_task(m.add_raster_async(byte, key="k", colormap="viridis"))
        second = asyncio.create_task(m.add_raster_async(byte, key="k", colormap="magma"))
        await wait_until(lambda: len(gates) == 2)
        gates[1].set()
        await second
        gates[0].set()
        assert await first is None and m.layer_store.get("k").style.colormap == "magma"

    asyncio.run(run())


@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize(
    "newer, expected",
    [
        ("panel_remove", None),
        ("panel_restyle", "gray"),
        ("sync_replace", "cividis"),
        ("remove_all", None),
        ("remove_layer", None),
    ],
)
def test_newer_action_beats_pending_wrapper(byte, monkeypatch, existing, newer, expected):
    if newer == "panel_restyle" and not existing:
        pytest.skip("nothing to restyle before the first add lands")
    gates = []

    async def slow_prepare(spec, **kw):
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return prepare_sync(spec, **kw)

    monkeypatch.setattr(sepal_map_module, "prepare", slow_prepare)

    async def run():
        m = SepalMap(gee=False)
        if existing:
            m.add_raster(byte, key="k", colormap="viridis")  # sync path: not gated
        pending = asyncio.create_task(m.add_raster_async(byte, key="k", colormap="magma"))
        await wait_until(lambda: len(gates) == 1)
        {
            "panel_remove": lambda: m.layer_store.remove("k", missing_ok=True),
            "panel_restyle": lambda: m.layer_store.restyle("k", colormap="gray"),
            "sync_replace": lambda: m.add_raster(byte, key="k", colormap="cividis"),
            "remove_all": lambda: m.remove_all(),
            "remove_layer": lambda: m.remove_layer("k", none_ok=True),
        }[newer]()
        gates[0].set()
        assert await pending is None
        assert (m.layer_store.get("k").style.colormap if "k" in m.layer_store else None) == expected

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["error", "cancel", "older_error"])
def test_wrapper_releases_its_reservation(byte, tmp_path, monkeypatch, outcome):
    gates = []

    async def slow_prepare(spec, **kw):
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return prepare_sync(spec, **kw)

    monkeypatch.setattr(sepal_map_module, "prepare", slow_prepare)

    async def run():
        m = SepalMap(gee=False)
        first = asyncio.create_task(
            m.add_raster_async(byte if outcome == "cancel" else tmp_path / "gone.tif", key="k")
        )
        await wait_until(lambda: len(gates) == 1)
        if outcome == "older_error":
            newer = asyncio.create_task(m.add_raster_async(byte, key="k"))
            await wait_until(lambda: len(gates) == 2)
        first.cancel() if outcome == "cancel" else gates[0].set()
        with pytest.raises((LayerPrepareError, asyncio.CancelledError)):
            await first
        assert set(m.layer_store.reserved()) == ({"k"} if outcome == "older_error" else set())
        if outcome == "older_error":
            gates[1].set()
            await newer
            assert "k" in m.layer_store and m.layer_store.reserved() == {}

    asyncio.run(run())


def test_hidden_layer_found_and_removed_by_name(byte):
    m = SepalMap(gee=False)
    m.add_raster(byte, layer_name="Elevation", key="dem")
    m.layer_store.set_visible("dem", False)
    assert m.find_layer("Elevation") is m.layer_engine.leaflet_layer("dem")
    m.remove_layer("Elevation")
    assert "dem" not in m.layer_store


def test_key_beats_name_across_raw_and_managed(byte):
    m = SepalMap(gee=False)
    m.add_raster(byte, layer_name="x", key="managed")
    raw = ipl.TileLayer(url="https://t/{z}/{x}/{y}", name="raw")
    raw.key = "x"
    m.add_layer(raw)
    assert m.find_layer("x") is raw


def test_raw_add_spares_a_managed_layer_named_like_its_key(byte):
    m = SepalMap(gee=False)
    m.add_raster(byte, layer_name="x", key="managed")
    m.add_layer(ipl.TileLayer(url="https://t/{z}/{x}/{y}", name="raw"), key="x")
    assert "managed" in m.layer_store
    m.add_layer(ipl.TileLayer(url="https://t/{z}/{x}/{y}", name="raw2"), key="managed")
    assert "managed" not in m.layer_store  # the same key replaces


def test_raw_tile_layer_goes_to_overlay_pane():
    m = SepalMap(gee=False)
    layer = ipl.TileLayer(url="https://t/{z}/{x}/{y}", name="raw")
    m.add_layer(layer)
    assert layer.pane == OVERLAY_PANE


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_aoi_overlay_stays_above_data(byte):
    async def run():
        m = SepalMap()
        await m.add_ee_layer_async(
            ee.FeatureCollection([ee.Feature(ee.Geometry.Point([0, 0]).buffer(1000))]),
            {},
            "aoi",
            overlay=True,
        )
        m.add_raster(byte, key="data")
        aoi = m.find_layer("aoi")
        assert aoi.pane == OVERLAY_PANE and "aoi" not in m.layer_store
        assert int(m.panes[OVERLAY_PANE]["zIndex"]) > int(
            m.panes[m.layer_engine.leaflet_layer("data").pane]["zIndex"]
        )

    asyncio.run(run())


def test_add_raster_goes_through_store(byte):
    m = SepalMap(gee=False)
    layer = m.add_raster(byte, layer_name="dem", key="dem")
    assert (
        m.layer_store.ids == ["dem"]
        and layer is m.layer_engine.leaflet_layer("dem")
        and layer.raster == str(byte.resolve())
    )


def test_same_key_replaces_in_place(byte):
    m = SepalMap(gee=False)
    m.add_raster(byte, key="a")
    m.add_raster(byte, key="b")
    m.add_raster(byte, key="a", colormap="magma")
    assert m.layer_store.ids == ["b", "a"] and m.layer_store.get("a").revision == 1


def test_remove_mixed_layers(byte, pmtiles_spec):
    m = SepalMap(gee=False)
    m.add_raster(byte, layer_name="managed", key="managed")
    m.add_layer(ipl.GeoJSON(data={"type": "FeatureCollection", "features": []}, name="raw"))
    m.layer_store.add(pmtiles_spec)
    m.layer_store.set_visible(pmtiles_spec.id, False)
    m.remove_layer(pmtiles_spec.id)  # hidden and detached, still removable by key
    m.remove_all(keep_names=["raw"])
    assert m.layer_store.ids == [] and [lyr.name for lyr in m.layers if not lyr.base] == ["raw"]


def test_managed_layers_follow_theme(fake_vector):
    theme = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme)
    m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v"))
    layer = m.layer_engine.leaflet_layer("v")
    before = layer.style["color"]
    theme.set_mode("dark")
    assert layer.style["color"] != before


@pytest.mark.parametrize("kind", ["geojson", "ee"])
def test_hidden_layer_follows_theme_when_shown(fake_vector, gee_spec, kind):
    theme = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme)
    if kind == "geojson":
        m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v"))
    else:
        spec = gee_spec.model_copy(update={"id": "v"})
        m.layer_engine.put(
            RenderLayer(
                render_hash=spec.render_hash,
                kind="raster-xyz",
                url="https://light/{z}/{x}/{y}",
                theme_urls={False: "https://light/{z}/{x}/{y}", True: "https://dark/{z}/{x}/{y}"},
            )
        )
        m.layer_store.add(spec)
    m.layer_store.set_visible("v", False)
    theme.set_mode("dark")
    m.layer_store.set_visible("v", True)
    layer = m.layer_engine.leaflet_layer("v")
    if kind == "geojson":
        assert layer.style["color"] == layer.point_style["color"] == THEMES[True]["primary"]
    else:
        assert layer.url.startswith("https://dark")

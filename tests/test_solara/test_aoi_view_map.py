"""AoiView draws the AOI as overlay layers of the map's store, and takes them off again."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import pytest
import reacton
import solara

import pysepal.mapping.sepal_map as sepal_map_module
import pysepal.solara.components.aoi.admin as admin_mod
import pysepal.solara.components.aoi.aoi_view as aoi_view_mod
from pysepal import mapping as sm
from pysepal.layers import RenderLayer, VectorStyle
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec
from pysepal.solara.components.aoi.aoi_view import AoiView
from pysepal.solara.components.aoi.constants import admin_source_attribution

from ._harness import wait_until

DATA = Path(__file__).resolve().parents[1] / "data" / "aoi_manual" / "manual_polygons.geojson"
SHAPE = AoiSpec(method="SHAPE", pathname=str(DATA))
ADMIN = AoiSpec(method="ADMIN0", admin_codes=("101",))
pytestmark = pytest.mark.usefixtures("empty_file_browser")


@pytest.fixture(autouse=True)
def _fake_admin(monkeypatch):
    """Admin items and results without the network."""
    items = {(0, ""): [{"title": "Algeria", "value": "101"}]}
    monkeypatch.setattr(
        admin_mod, "fetch_admin_items", lambda level, parent_code="": items.get((level, ""), [])
    )

    async def process_admin(method, admin_code, gee=True, gee_interface=None, admin_codes=()):
        return AoiResult(
            method=method,
            name="DZA",
            admin=admin_code,
            gee=gee,
            feature_collection=object() if gee else None,
            spec=AoiSpec(method=method, admin_codes=tuple(admin_codes)),
        )

    async def bounds(level, admin_code):
        return (1.0, 2.0, 3.0, 4.0)

    monkeypatch.setattr(aoi_view_mod, "process_admin", process_admin)
    monkeypatch.setattr(aoi_view_mod, "fetch_admin_bounds_async", bounds)


def layer_of(m, layer_id):
    return next((x for x in m.state.get("layers", ()) if x["id"] == layer_id), None)


def _run(scenario, *, gee=False, **props):
    """Render an AoiView on a new map, on a live loop, while ``scenario(m, clear)`` runs."""

    async def run():
        m = sm.SepalMap(gee=False)
        if gee:
            # an Earth Engine map, without Earth Engine
            m.gee, m.gee_interface = True, None
        clear_ref = SimpleNamespace(current=None)

        @solara.component
        def Harness():
            AoiView(map_=m, gee=gee, clear_ref=clear_ref, **props)

        _root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await scenario(m, lambda: clear_ref.current())
        finally:
            rc.close()

    asyncio.run(run())


async def _drawn(m, layer_id):
    """The published layer, once the engine prepared and drew it."""
    await wait_until(lambda: m.layer_engine.accepted(layer_id) is not None)
    await m.layer_engine.wait_idle()
    m.layer_engine.flush()
    return layer_of(m, layer_id)


def test_a_vector_aoi_is_an_overlay_layer_of_the_store():
    spec = solara.reactive(SHAPE)

    async def scenario(m, clear):
        store = m.layer_store
        await wait_until(lambda: "aoi" in store)
        layer = store.get("aoi")
        assert (layer.zone, layer.name) == ("overlay", "manual_polygons")
        # aoi.json, with the colours that follow the theme left to the map
        assert layer.style == VectorStyle(fill_opacity=0.4, width=2)
        # the fit uses the AOI's own bounds, so it never waits for the prepare
        west, south, east, north = gpd.read_file(DATA).to_crs(4326).total_bounds
        assert m.view_request["bounds"] == pytest.approx([west, south, east, north])

        drawn = await _drawn(m, "aoi")
        assert drawn["zone"] == "overlay" and drawn["paint"]["fill_opacity"] == 0.4

        # a new AOI replaces it
        spec.set(AoiSpec(method="SHAPE", pathname=str(DATA), column="region", value="north"))
        await wait_until(lambda: "aoi" in store and store.get("aoi").name != "manual_polygons")
        assert store.ids == ["aoi"] and store.get("aoi").name == "manual_polygons_north"

        clear()
        assert store.ids == []

    _run(scenario, spec=spec)


def test_a_caller_style_is_mapped_onto_the_vector_style():
    red = VectorStyle(stroke="red").stroke

    async def scenario(m, clear):
        await wait_until(lambda: "aoi" in m.layer_store)
        style = m.layer_store.get("aoi").style
        assert style.width == 4 and style.stroke == red
        # Leaflet's fill: the stroke colour at 0.2
        assert (style.fill, style.fill_opacity) == (red, 0.2)

    _run(scenario, spec=SHAPE, map_style={"color": "red", "weight": 4, "dashArray": "3"})


@pytest.mark.parametrize(
    "map_style, fill, fill_opacity",
    [
        ({"color": "blue"}, "blue", 0.2),
        ({"color": "blue", "fillColor": "red", "fillOpacity": 0.5}, "red", 0.5),
        ({"weight": 1}, None, 0.2),
    ],
)
def test_a_caller_style_gets_leaflets_default_fill(map_style, fill, fill_opacity):
    expected = VectorStyle(fill=fill).fill

    async def scenario(m, clear):
        await wait_until(lambda: "aoi" in m.layer_store)
        style = m.layer_store.get("aoi").style
        assert (style.fill, style.fill_opacity) == (expected, fill_opacity)
        assert (await _drawn(m, "aoi"))["paint"]["fill_opacity"] == fill_opacity

    _run(scenario, spec=SHAPE, map_style=map_style)


def test_an_outline_only_style_draws_no_fill():
    style = {"fill": False, "fillColor": "red", "fillOpacity": 1, "color": "blue", "weight": 4}

    async def scenario(m, clear):
        await wait_until(lambda: "aoi" in m.layer_store)
        assert (await _drawn(m, "aoi"))["paint"]["fill_opacity"] == 0

    _run(scenario, spec=SHAPE, map_style=style)


def test_an_admin_aoi_adds_its_preview_and_fits_the_admin_bounds():
    async def scenario(m, clear):
        store = m.layer_store
        await wait_until(lambda: m.view_request.get("bounds") == [1.0, 2.0, 3.0, 4.0])
        preview = store.get("aoi_preview")
        assert (preview.zone, preview.name) == ("overlay", "aoi")
        assert preview.attribution == admin_source_attribution(gee=False)
        assert "CQL_FILTER=gaul0_code=101" in preview.source.url
        assert "LAYERS=gaul:gaul_2024_l0" in preview.source.url
        assert "{bbox-epsg-3857}" in preview.source.url
        assert (await _drawn(m, "aoi_preview"))["zone"] == "overlay"

        clear()
        assert "aoi_preview" not in store

    _run(scenario, spec=ADMIN)


@pytest.mark.parametrize(
    "spec, gated",
    [(ADMIN, "process_admin"), (ADMIN, "fetch_admin_bounds_async"), (SHAPE, "process_shape")],
)
def test_clearing_during_an_await_leaves_nothing_on_the_map(monkeypatch, spec, gated):
    gate, started = asyncio.Event(), []
    real = getattr(aoi_view_mod, gated)

    async def slow(*args, **kwargs):
        started.append(True)
        await gate.wait()
        return await real(*args, **kwargs)

    monkeypatch.setattr(aoi_view_mod, gated, slow)

    async def scenario(m, clear):
        await wait_until(lambda: started)
        seq = m.view_request["seq"]
        clear()
        gate.set()
        await asyncio.sleep(0.1)
        assert m.layer_store.ids == [] and m.layer_store.reserved() == {}
        assert m.view_request["seq"] == seq

    _run(scenario, spec=spec)


def test_a_clear_on_the_run_own_stack_stops_it_adding(monkeypatch):
    """Such a clear cannot cancel the run it lands in; the run must still add nothing."""
    trigger = solara.reactive(False)
    real = aoi_view_mod.process_admin

    async def process_admin(*args, **kwargs):
        result = await real(*args, **kwargs)
        trigger.set(True)  # renders here, so the clear runs inside this coroutine
        return result

    monkeypatch.setattr(aoi_view_mod, "process_admin", process_admin)

    async def run():
        m = sm.SepalMap(gee=False)
        clear_ref = SimpleNamespace(current=None)

        @solara.component
        def Harness():
            def clear_once():
                if trigger.value:
                    clear_ref.current()

            solara.use_effect(clear_once, [trigger.value])
            AoiView(map_=m, gee=False, clear_ref=clear_ref, spec=ADMIN)

        _root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await wait_until(lambda: trigger.value)
            await asyncio.sleep(0.1)
            assert m.layer_store.ids == [] and "bounds" not in m.view_request
        finally:
            rc.close()

    asyncio.run(run())


class _SlowBounds:
    def __init__(self) -> None:
        """Answer the bounds lookup once ``gate`` is set."""
        self.gate = asyncio.Event()
        self.calls = 0

    async def get_bounds_async(self, item):
        self.calls += 1
        await self.gate.wait()
        return (1.0, 2.0, 3.0, 4.0)


@pytest.mark.parametrize("stage", ["prepare", "zoom"])
def test_clearing_during_the_earth_engine_add_leaves_nothing_on_the_map(
    monkeypatch, gee_spec, stage
):
    gate, started = asyncio.Event(), []
    spec = gee_spec.model_copy(update={"id": "aoi", "name": "aoi"})

    async def prepare(spec, **kwargs):
        started.append(True)
        if stage == "prepare":
            await gate.wait()
        url = "https://ee.test/{z}/{x}/{y}"
        return RenderLayer(render_hash=spec.render_hash, kind="raster-xyz", url=url, ee_object=1)

    monkeypatch.setattr(sepal_map_module, "prepare", prepare)
    monkeypatch.setattr(sm.SepalMap, "_ee_spec", lambda self, *args, **kwargs: spec)
    monkeypatch.setattr(aoi_view_mod, "get_current_gee_interface", lambda: None)
    monkeypatch.setattr(aoi_view_mod.su, "init_ee", lambda: None)
    bounds = _SlowBounds()

    async def scenario(m, clear):
        m.layer_engine.gee_interface = bounds
        await wait_until(lambda: started)
        if stage == "zoom":
            await wait_until(lambda: bounds.calls == 1)
            assert m.layer_store.get("aoi").zone == "overlay"
        seq = m.view_request["seq"]
        clear()
        gate.set()
        bounds.gate.set()
        await asyncio.sleep(0.1)
        assert m.layer_store.ids == [] and m.layer_store.reserved() == {}
        assert m.view_request["seq"] == seq

    _run(scenario, gee=True, spec=ADMIN)


def test_the_earth_engine_aoi_fits_once(monkeypatch, gee_spec):
    spec = gee_spec.model_copy(update={"id": "aoi", "name": "aoi"})

    async def prepare(spec, **kwargs):
        url = "https://ee.test/{z}/{x}/{y}"
        return RenderLayer(render_hash=spec.render_hash, kind="raster-xyz", url=url, ee_object=1)

    monkeypatch.setattr(sepal_map_module, "prepare", prepare)
    monkeypatch.setattr(sm.SepalMap, "_ee_spec", lambda self, *args, **kwargs: spec)
    monkeypatch.setattr(aoi_view_mod, "get_current_gee_interface", lambda: None)
    monkeypatch.setattr(aoi_view_mod.su, "init_ee", lambda: None)
    bounds = _SlowBounds()
    bounds.gate.set()

    async def scenario(m, clear):
        m.layer_engine.gee_interface = bounds
        seq = m.view_request["seq"]
        await wait_until(lambda: m.view_request["seq"] > seq)
        await asyncio.sleep(0.05)
        assert m.view_request["seq"] == seq + 1
        assert m.view_request["bounds"] == [1.0, 2.0, 3.0, 4.0]
        assert m.layer_store.get("aoi").zone == "overlay"
        assert "aoi_preview" not in m.layer_store

    _run(scenario, gee=True, spec=ADMIN)

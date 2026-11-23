"""Tests of the engine drawing a LayerStore on a MapLibre widget."""

import asyncio
import inspect
import json
import logging
import os
import threading
import time
from pathlib import Path

import ee
import pytest
from eeclient.exceptions import EERestException
from pysepal_map import Basemap, Controls, MapState, MapWidget

import pysepal.mapping.maplibre_engine as maplibre_engine
from pysepal.frontend.styles import THEMES
from pysepal.layers import (
    LayerPrepareError,
    LayerSpec,
    LayerStore,
    Legend,
    LegendItem,
    RasterStyle,
    RenderLayer,
    TileSource,
    VectorStyle,
    local_fingerprint,
    uri_to_path,
)
from pysepal.mapping.maplibre_engine import MapLibreEngine
from tests.test_solara._harness import wait_until

# ---------------------------------------------------------------------------
# Views, simulated through the widget's own message handler
# ---------------------------------------------------------------------------


def msg(widget: MapWidget, **content) -> None:
    widget._handle_custom_msg(content, [])


def open_view(widget: MapWidget, view: str = "a") -> None:
    msg(widget, type="view_open", view_id=view, side="main")


def close_view(widget: MapWidget, view: str = "a") -> None:
    msg(widget, type="view_close", view_id=view, side="main")


def layer_of(widget: MapWidget, layer_id: str) -> dict | None:
    return next((x for x in widget.state.get("layers", ()) if x["id"] == layer_id), None)


def ids_of(widget: MapWidget) -> list[str]:
    return [x["id"] for x in widget.state.get("layers", ())]


def report(widget, layer_id, status, view="a", error=None, token=None, instance=None) -> None:
    """Send a view's status on the drawn instance of a layer, or on the one given."""
    current = layer_of(widget, layer_id)
    msg(
        widget,
        type="status",
        view_id=view,
        side="main",
        id=layer_id,
        token=current["token"] if token is None else token,
        instance=current["instance"] if instance is None else instance,
        status=status,
        error=error,
    )


def pulled(widget: MapWidget, digest: str) -> bytes | None:
    """Pull ``digest`` as a view would: the bytes of the reply, or None if missing."""
    sent = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(widget, "send", lambda content, buffers=None: sent.append((content, buffers)))
        msg(widget, type="pull", digests=[digest])
    [(content, buffers)] = sent
    return None if content.get("missing") else buffers[0]


# ---------------------------------------------------------------------------
# Made-up specs and renders
# ---------------------------------------------------------------------------


def collection(x: float) -> dict:
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Point", "coordinates": [x, 0]},
    }
    return {"type": "FeatureCollection", "features": [feature]}


def payload(data: dict) -> bytes:
    return json.dumps(data, separators=(",", ":")).encode()


def write_point(path: Path, x: float) -> None:
    """Write a one-point FeatureCollection with a later mtime than before."""
    before = path.stat().st_mtime_ns if path.exists() else time.time_ns()
    path.write_text(json.dumps(collection(x)))
    later = max(path.stat().st_mtime_ns, before) + 1_000_000_000
    os.utime(path, ns=(later, later))


def tile_spec(layer_id: str, url: str | None = None, **kw) -> LayerSpec:
    url = url or f"https://tiles.test/{layer_id}/{{z}}/{{x}}/{{y}}.png"
    return LayerSpec.from_tiles(url, name=layer_id, id=layer_id, **kw)


def vector_spec(layer_id: str, uri: str | None = None, **style) -> LayerSpec:
    uri = uri or f"https://data.test/{layer_id}.geojson"
    return LayerSpec.from_vector(uri, name=layer_id, id=layer_id, **style)


class FakePrepare:
    """Made-up renders in place of ``prepare`` and ``prepare_sync``.

    Tile URLs carry the render hash, so a restyle changes them; GeoJSON comes from
    ``data`` (by URI), from the local file, or is one point at the origin.
    """

    def __init__(self) -> None:
        """Start with no data, error, override or gate."""
        self.data: dict[str, dict] = {}
        self.errors: dict[str, str] = {}
        self.overrides: dict[str, dict] = {}
        self.gates: dict[str, list[asyncio.Event]] = {}
        self.calls: list[tuple[str, asyncio.AbstractEventLoop | None]] = []

    def hold(self, layer_id: str) -> asyncio.Event:
        """Make the next async prepare of ``layer_id`` wait for the returned event."""
        gate = asyncio.Event()
        self.gates.setdefault(layer_id, []).append(gate)
        return gate

    def render(self, spec: LayerSpec) -> RenderLayer:
        if spec.id in self.errors:
            raise LayerPrepareError(f"{spec.name}: {self.errors[spec.id]}", layer_id=spec.id)
        source, extra = spec.source, self.overrides.get(spec.id, {})
        fields = {"render_hash": spec.render_hash, "fingerprint": local_fingerprint(spec)}
        if source.type == "vector" and source.format == "PMTiles":
            fields |= {"kind": "pmtiles", "url": source.uri, "source_layer": source.layer}
        elif source.type == "vector":
            if source.uri in self.data:
                data = self.data[source.uri]
            elif source.uri.startswith("file:"):
                data = json.loads(uri_to_path(source.uri).read_text())
            else:
                data = collection(0)
            fields |= {"kind": "geojson", "data": data, "bounds": (0.0, 0.0, 1.0, 1.0)}
        elif source.type == "tile":
            url = f"{source.url}?style={spec.render_hash[:8]}"
            fields |= {"kind": "raster-xyz", "url": url, "tile_size": source.tile_size}
            fields |= {"max_zoom": source.max_zoom}
        else:  # an Earth Engine image
            url = f"https://ee.test/{spec.render_hash[:8]}/{{z}}/{{x}}/{{y}}"
            fields |= {"kind": "raster-xyz", "url": url, "ee_object": f"ee:{spec.id}"}
        if source.type == "vector":
            fields["vector_style"] = spec.style
        return RenderLayer(**{**fields, **extra})

    def sync(self, spec: LayerSpec, *, gee_interface=None, **kw) -> RenderLayer:
        self.calls.append((spec.id, None))
        return self.render(spec)

    async def run(self, spec: LayerSpec, *, gee_interface=None, **kw) -> RenderLayer:
        self.calls.append((spec.id, asyncio.get_running_loop()))
        gates = self.gates.get(spec.id)
        if gates:
            await gates.pop(0).wait()
        return self.render(spec)


@pytest.fixture
def fake(monkeypatch) -> FakePrepare:
    fake = FakePrepare()
    monkeypatch.setattr(maplibre_engine, "prepare", fake.run)
    monkeypatch.setattr(maplibre_engine, "prepare_sync", fake.sync)
    return fake


class FakeGee:
    """Answers bounds lookups in order: a tuple is returned, an exception raised."""

    def __init__(self, *answers) -> None:
        """Keep the answers to give, first one first."""
        self.answers = list(answers)
        self.calls = 0

    def _next(self):
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def get_bounds(self, item):
        return self._next()

    async def get_bounds_async(self, item):
        return self._next()


def headless(**kw) -> tuple[MapWidget, LayerStore, MapLibreEngine]:
    widget, store = MapWidget(), LayerStore()
    return widget, store, MapLibreEngine(widget, store, **kw)


def on_loop(**kw) -> tuple[MapWidget, LayerStore, MapLibreEngine]:
    loop = asyncio.get_running_loop()
    widget, store = MapWidget(loop=loop), LayerStore()
    return widget, store, MapLibreEngine(widget, store, loop=loop, **kw)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def test_draws_in_drawing_order(fake):
    widget, store, _ = headless()
    store.add(tile_spec("d2"))
    store.add(tile_spec("o1", zone="overlay"))
    store.add(tile_spec("d1"))
    assert store.ids == ["d1", "o1", "d2"]
    assert ids_of(widget) == ["o1", "d1", "d2"]
    assert layer_of(widget, "o1")["zone"] == "overlay"
    assert layer_of(widget, "d1")["zone"] == "data"


def test_hidden_layer_stays_in_state(fake):
    widget, store, _ = headless()
    store.add(tile_spec("a"), visible=False)
    store.add(vector_spec("v"), opacity=0.4)
    assert layer_of(widget, "a")["visible"] is False
    assert layer_of(widget, "v")["opacity"] == 0.4
    store.set_visible("a", True)
    assert layer_of(widget, "a")["visible"] is True


@pytest.mark.asyncio
async def test_burst_publishes_once_per_tick(fake):
    widget, store, engine = on_loop()
    store.add(tile_spec("a"))
    await engine.wait_idle()
    revision = widget.state["revision"]
    for i in range(10):
        store.set_opacity("a", i / 10)
    assert widget.state["revision"] == revision
    await engine.wait_idle()
    assert widget.state["revision"] == revision + 1
    assert layer_of(widget, "a")["opacity"] == 0.9


@pytest.mark.asyncio
async def test_configure_updates_only_the_given_arguments(fake):
    widget, _, engine = on_loop()
    await engine.wait_idle()
    revision = widget.state["revision"]
    basemap = Basemap(("https://base.test/{z}/{x}/{y}.png",), attribution="base")
    engine.configure(basemap=basemap)
    engine.configure(theme="dark")
    engine.configure(controls=Controls(scale=False))
    await engine.wait_idle()
    assert widget.state["revision"] == revision + 1
    assert widget.state["basemap"] == basemap.to_json()
    assert widget.state["theme"] == "dark"
    assert widget.state["controls"] == Controls(scale=False).to_json()
    engine.configure(basemap=None)
    await engine.wait_idle()
    assert widget.state["basemap"] is None
    assert widget.state["theme"] == "dark"
    with pytest.raises(ValueError):
        engine.configure(theme="blue")


def test_put_seeds_the_cache_and_accepted_reports_the_drawn_pair(fake):
    widget, store, engine = headless()
    spec = tile_spec("a")
    render = fake.render(spec)
    engine.put(render)
    assert engine.accepted("a") is None
    store.add(spec)
    assert fake.calls == []
    drawn_spec, drawn_render = engine.accepted("a")
    assert drawn_render is render
    assert drawn_spec.render_hash == spec.render_hash


def test_restyle_keeps_instance_and_digest(fake):
    widget, store, _ = headless()
    store.add(vector_spec("v"))
    before = layer_of(widget, "v")
    store.restyle("v", stroke="#ff0000", width=4)
    after = layer_of(widget, "v")
    assert after["instance"] == before["instance"]
    assert after["token"] == before["token"]
    assert after["source"]["digest"] == before["source"]["digest"]
    assert after["paint"]["stroke"] == "#ff0000"
    assert after["paint"]["fill"] == "#ff0000"
    assert after["paint"]["width"] == 4
    assert fake.calls == [("v", None)]


def test_overwritten_file_bumps_the_token(fake, tmp_path):
    path = tmp_path / "v.geojson"
    write_point(path, 0)
    widget, store, _ = headless()
    spec = LayerSpec.from_vector(path, id="v")
    store.add(spec)
    before = layer_of(widget, "v")
    write_point(path, 0)  # the same bytes, a new modification time
    store.add(spec, replace=True)
    after = layer_of(widget, "v")
    assert after["source"] == before["source"]
    assert after["token"] == before["token"] + 1
    assert after["instance"] != before["instance"]


def test_fresh_remote_prepare_bumps_the_token(fake):
    widget, store, _ = headless()
    url = "https://tiles.test/t/{z}/{x}/{y}.png"
    fake.overrides["t"] = {"url": url}
    store.add(tile_spec("t", url=url))
    before = layer_of(widget, "t")
    store.restyle("t", colormap="magma")  # prepared again: the same URL, a fresh read
    after = layer_of(widget, "t")
    assert len(fake.calls) == 2
    assert after["source"] == before["source"]
    assert after["token"] == before["token"] + 1
    assert after["instance"] != before["instance"]
    store.update("t", store.get("t").revise(attribution="cached"))  # served from the cache
    assert layer_of(widget, "t")["token"] == after["token"]


@pytest.mark.asyncio
async def test_stale_prepare_is_dropped(fake):
    widget, store, engine = on_loop()
    old = "https://tiles.test/old/{z}/{x}/{y}.png"
    new = "https://tiles.test/new/{z}/{x}/{y}.png"
    gate = fake.hold("a")
    store.add(tile_spec("a", url=old))
    await wait_until(lambda: len(fake.calls) == 1)
    store.add(tile_spec("a", url=new), replace=True)
    await wait_until(lambda: layer_of(widget, "a") is not None)
    gate.set()
    await engine.wait_idle()
    [tiles] = layer_of(widget, "a")["source"]["tiles"]
    assert tiles.startswith(new)
    assert store.view("a").status == "ready"


@pytest.mark.asyncio
async def test_failed_replacement_keeps_the_previous_render(fake):
    widget, store, engine = on_loop()
    store.add(tile_spec("a"))
    store.add(tile_spec("b"))
    await engine.wait_idle()
    before, other = layer_of(widget, "a"), layer_of(widget, "b")
    fake.errors["a"] = "server down"
    store.restyle("a", colormap="magma")
    store.restyle("b", colormap="magma")
    store.set_opacity("b", 0.5)
    await engine.wait_idle()
    assert store.view("a").status == "error"
    assert store.view("a").error == "a: server down"
    assert layer_of(widget, "a") == before
    assert layer_of(widget, "b")["source"] != other["source"]
    assert layer_of(widget, "b")["opacity"] == 0.5
    assert store.view("b").status == "ready"


def test_failed_replacement_keeps_the_accepted_zone_and_legend(fake):
    widget, store, engine = headless()
    old = Legend(title="old", items=[LegendItem(label="x", color="#ff0000")])
    new = Legend(title="new", items=[LegendItem(label="y", color="#00ff00")])
    fake.overrides["a"] = {"legend": old}
    store.add(tile_spec("a"))
    store.add(tile_spec("o", zone="overlay"))
    store.move("a", 0)
    assert ids_of(widget) == ["o", "a"]
    assert store.view("a").legend == old
    fake.overrides["a"] = {"legend": new}
    fake.errors["a"] = "boom"
    replacement = store.get("a").revise(zone="overlay", style=RasterStyle(colormap="magma"))
    store.update("a", replacement)
    assert store.drawing_order() == ["a", "o"]
    assert ids_of(widget) == ["o", "a"]
    assert layer_of(widget, "a")["zone"] == "data"
    view = store.view("a")
    assert (view.status, view.error) == ("error", "a: boom")
    assert view.legend == old
    assert view.kind == "raster-xyz"
    assert engine.accepted("a")[0].zone == "data"


def test_rejected_first_add_stays_absent(fake):
    widget, store, _ = headless()
    store.add(tile_spec("a"))
    store.add(vector_spec("v", width=-1))
    assert store.view("v").status == "error"
    assert "width" in store.view("v").error
    assert ids_of(widget) == ["a"]
    store.add(tile_spec("b"))
    assert ids_of(widget) == ["b", "a"]


def test_a_layer_must_build_under_both_themes(fake):
    widget, store, engine = headless()
    light = "https://light.test/{z}/{x}/{y}"
    fake.overrides["e"] = {"url": light, "theme_urls": {False: light}}
    store.add(tile_spec("e"))
    store.add(tile_spec("a"))
    assert store.view("e").status == "error"
    assert ids_of(widget) == ["a"]
    engine.configure(theme="dark")
    assert ids_of(widget) == ["a"]


@pytest.mark.parametrize("change", [{"width": -1}, {"fill_opacity": 1.5}])
def test_rejected_replacement_keeps_the_old_layer(fake, change):
    widget, store, _ = headless()
    store.add(vector_spec("v", stroke="#00ff00"))
    before = layer_of(widget, "v")
    store.restyle("v", **change)
    assert layer_of(widget, "v") == before
    assert store.view("v").status == "error"
    assert next(iter(change)) in store.view("v").error


def test_attribution_only_edit_reaches_the_map(fake):
    widget, store, _ = headless()
    store.add(tile_spec("a", attribution="old"))
    before = layer_of(widget, "a")
    store.update("a", store.get("a").revise(attribution="new"))
    after = layer_of(widget, "a")
    assert after["attribution"] == "new"
    assert after["token"] == before["token"]
    assert len(fake.calls) == 1


def test_remote_vector_reread_gets_a_new_digest(fake):
    widget, store, _ = headless()
    uri = "https://data.test/v.geojson"
    fake.data[uri] = collection(0)
    store.add(vector_spec("v", uri=uri))
    before = layer_of(widget, "v")
    fake.data[uri] = collection(10)
    store.remove("v")
    store.add(vector_spec("v", uri=uri, stroke="#ff0000"))  # not cached: read again
    after = layer_of(widget, "v")
    assert len(fake.calls) == 2
    assert after["source"]["digest"] != before["source"]["digest"]
    assert after["instance"] != before["instance"]
    assert pulled(widget, after["source"]["digest"]) == payload(collection(10))


@pytest.mark.asyncio
async def test_payload_survives_a_nested_draw(fake):
    widget, store, engine = on_loop()
    store.add(vector_spec("v"))
    await engine.wait_idle()
    nested = []

    def draw_over(_change):
        if not nested:
            nested.append(True)
            widget.publish(MapState())  # prunes the engine's payload

    widget.observe(draw_over, "state")
    store.set_opacity("v", 0.5)
    await engine.wait_idle()
    widget.unobserve(draw_over, "state")
    assert nested and ids_of(widget) == []
    engine.flush()
    layer = layer_of(widget, "v")
    assert layer["opacity"] == 0.5
    assert pulled(widget, layer["source"]["digest"]) == payload(collection(0))


def test_seventeen_geojson_layers_all_served(fake):
    widget, store, _ = headless()
    for i in range(17):
        uri = f"https://data.test/{i}.geojson"
        fake.data[uri] = collection(i)
        store.add(vector_spec(f"v{i}", uri=uri))
    layers = widget.state["layers"]
    assert len({x["source"]["digest"] for x in layers}) == 17
    for x in layers:
        i = int(x["id"][1:])
        assert pulled(widget, x["source"]["digest"]) == payload(collection(i))


def test_geojson_payload_added_once(fake, monkeypatch):
    widget, store, engine = headless()
    added = []
    add_payload = widget.add_payload
    monkeypatch.setattr(widget, "add_payload", lambda data: added.append(data) or add_payload(data))
    store.add(vector_spec("v"))
    for _ in range(3):
        engine.flush()
    assert added == [payload(collection(0))]


def test_geojson_bytes_are_serialized_once_per_prepare(fake, monkeypatch):
    widget, store, _ = headless()
    serialized = []
    real = maplibre_engine._geojson_bytes
    monkeypatch.setattr(
        maplibre_engine, "_geojson_bytes", lambda data: serialized.append(data) or real(data)
    )
    store.add(vector_spec("v"))
    before = layer_of(widget, "v")
    store.update("v", store.get("v").revise(zone="overlay"))  # served from the cache
    store.update("v", store.get("v").revise(attribution="edited"))
    store.add(store.get("v"), replace=True)
    store.restyle("v", stroke="#ff0000")  # restyled: shares the data
    store.restyle("v", stroke=None)  # back to the cached style
    assert len(fake.calls) == 1
    assert len(serialized) == 1
    after = layer_of(widget, "v")
    assert after["source"] == before["source"]
    assert pulled(widget, after["source"]["digest"]) == payload(collection(0))


def test_pmtiles_without_source_layer_is_an_error(fake):
    widget, store, _ = headless()
    store.add(LayerSpec.from_vector("https://x.org/a.pmtiles", id="bare", name="bare"))
    store.add(LayerSpec.from_vector("https://x.org/b.pmtiles", id="ok", layer="roads", name="ok"))
    view = store.view("bare")
    assert (view.status, view.error) == ("error", "PMTiles layer needs a source layer")
    assert ids_of(widget) == ["ok"]
    assert layer_of(widget, "ok")["source"] == {
        "url": "https://x.org/b.pmtiles",
        "source_layer": "roads",
    }


def test_theme_switch_swaps_urls_and_default_stroke(fake):
    widget, store, engine = headless()
    light, dark = "https://light.test/{z}/{x}/{y}", "https://dark.test/{z}/{x}/{y}"
    fake.overrides["e"] = {"url": light, "theme_urls": {False: light, True: dark}}
    store.add(tile_spec("e"))
    store.add(vector_spec("v"))
    store.add(vector_spec("s", stroke="#123456"))
    assert layer_of(widget, "e")["source"]["tiles"] == [light]
    paint = layer_of(widget, "v")["paint"]
    assert paint["stroke"] == paint["fill"] == THEMES[False]["primary"]
    instances = {x["id"]: x["instance"] for x in widget.state["layers"]}
    engine.configure(theme="dark")
    assert widget.state["theme"] == "dark"
    assert layer_of(widget, "e")["source"]["tiles"] == [dark]
    paint = layer_of(widget, "v")["paint"]
    assert paint["stroke"] == paint["fill"] == THEMES[True]["primary"]
    assert layer_of(widget, "s")["paint"]["stroke"] == "#123456"
    assert layer_of(widget, "v")["instance"] == instances["v"]


def test_tile_size_and_native_zoom_reach_the_source(fake):
    widget, store, _ = headless()
    source = TileSource(url="https://big.test/{z}/{x}/{y}.png", tile_size=512, max_zoom=24)
    store.add(LayerSpec.from_tiles(source, name="big", id="big"))
    fake.overrides["local"] = {"max_zoom": 20, "bounds": (1.0, 2.0, 3.0, 4.0)}
    store.add(tile_spec("local"))
    big, local = layer_of(widget, "big"), layer_of(widget, "local")
    assert big["source"]["tile_size"] == 512
    assert big["source"]["max_native_zoom"] == 24
    assert big["max_zoom"] is None
    assert local["source"]["tile_size"] == 256
    assert local["source"]["max_native_zoom"] == 20
    assert local["source"]["bounds"] == [1.0, 2.0, 3.0, 4.0]
    assert local["max_zoom"] is None


def test_replace_with_another_kind_changes_instance_and_paint(fake):
    widget, store, _ = headless()
    store.add(vector_spec("x"))
    before = layer_of(widget, "x")
    store.add(tile_spec("x"), replace=True)
    raster = layer_of(widget, "x")
    assert raster["kind"] == "raster" and raster["paint"] is None
    assert raster["instance"] != before["instance"]
    assert raster["token"] == before["token"] + 1
    store.add(vector_spec("x", stroke="#123456"), replace=True)
    vector = layer_of(widget, "x")
    assert vector["kind"] == "geojson"
    assert vector["paint"]["stroke"] == "#123456"
    assert vector["instance"] != raster["instance"]


def test_zone_only_change_on_a_cached_remote_layer_keeps_the_instance(fake):
    widget, store, _ = headless()
    store.add(tile_spec("a"))
    store.add(tile_spec("d"))
    assert ids_of(widget) == ["d", "a"]
    before = layer_of(widget, "a")
    store.update("a", store.get("a").revise(zone="overlay"))
    after = layer_of(widget, "a")
    assert ids_of(widget) == ["a", "d"]
    assert after["zone"] == "overlay"
    assert (after["token"], after["instance"]) == (before["token"], before["instance"])
    assert len(fake.calls) == 2


# ---------------------------------------------------------------------------
# Loops
# ---------------------------------------------------------------------------


def test_construction_without_a_loop_then_first_mount(fake):
    widget, store, engine = headless()
    store.add(tile_spec("a"))
    assert ids_of(widget) == ["a"]
    assert fake.calls == [("a", None)]

    async def mount():
        loop = asyncio.get_running_loop()
        open_view(widget)
        assert widget.loop is loop
        revision = widget.state["revision"]
        store.add(tile_spec("b"))
        assert widget.state["revision"] == revision
        await engine.wait_idle()
        assert ids_of(widget) == ["b", "a"]
        assert fake.calls[-1] == ("b", loop)

    asyncio.run(mount())


@pytest.mark.asyncio
async def test_loop_replaced_with_dirty_work(fake):
    loop, old = asyncio.get_running_loop(), asyncio.new_event_loop()
    widget, store = MapWidget(loop=loop), LayerStore()
    engine = MapLibreEngine(widget, store, loop=old)
    spec = tile_spec("a")
    engine.put(fake.render(spec))
    store.add(spec)  # accepted at once, its draw pending on the old loop
    await asyncio.sleep(0)
    assert ids_of(widget) == []
    old.close()
    store.set_opacity("a", 0.5)
    await engine.wait_idle()
    assert ids_of(widget) == ["a"]
    assert layer_of(widget, "a")["opacity"] == 0.5


def test_closed_loop_prepare_is_requested_again(fake):
    old = asyncio.new_event_loop()
    widget, store = MapWidget(), LayerStore()
    engine = MapLibreEngine(widget, store, loop=old)
    fake.hold("a")
    store.add(tile_spec("a"))
    old.run_until_complete(asyncio.sleep(0))  # the prepare starts and waits
    assert fake.calls == [("a", old)]
    # a shutdown, as asyncio.run and a kernel do it: cancel, drain, close
    tasks = asyncio.all_tasks(old)
    for task in tasks:
        task.cancel()
    old.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    old.close()
    assert store.view("a").status == "pending"

    async def resume():
        await engine.wait_idle()
        assert fake.calls[-1] == ("a", asyncio.get_running_loop())

    asyncio.run(resume())
    assert ids_of(widget) == ["a"]
    assert store.view("a").status == "ready"


def test_a_prepare_stranded_on_a_closed_loop_is_closed(fake):
    old = asyncio.new_event_loop()
    widget, store = MapWidget(), LayerStore()
    engine = MapLibreEngine(widget, store, loop=old)
    store.add(tile_spec("a"))
    [task] = asyncio.all_tasks(old)
    old.close()  # without running it: the prepare never started
    task._log_destroy_pending = False  # asyncio's own log of a pending task
    asyncio.run(engine.wait_idle())
    assert inspect.getcoroutinestate(task.get_coro()) == inspect.CORO_CLOSED
    assert ids_of(widget) == ["a"]


def test_engines_adopting_different_loops_do_not_both_write(fake, caplog):
    store, first, second = LayerStore(), MapWidget(), MapWidget()
    MapLibreEngine(first, store)
    MapLibreEngine(second, store)
    store.add(tile_spec("t"))
    loop_a, loop_b = asyncio.new_event_loop(), asyncio.new_event_loop()

    async def on(widget, action, *args, **kw):
        action(widget, *args, **kw)

    try:
        loop_a.run_until_complete(on(first, open_view))
        loop_a.run_until_complete(on(first, report, "t", "ready"))
        assert store.view("t").status == "ready"
        with caplog.at_level(logging.ERROR, logger="sepalui.mapping"):
            loop_b.run_until_complete(on(second, open_view))
        assert any("one loop" in r.getMessage() for r in caplog.records)
        revision = second.state["revision"]
        loop_b.run_until_complete(on(second, report, "t", "error", error="tile 500"))
        store.set_opacity("t", 0.5)
        loop_b.run_until_complete(asyncio.sleep(0))
        loop_a.run_until_complete(asyncio.sleep(0))
        assert second.state["revision"] == revision
        assert layer_of(first, "t")["opacity"] == 0.5
        assert store.view("t").status == "ready"
    finally:
        loop_a.close()
        loop_b.close()


def test_registering_on_a_store_another_live_loop_uses_raises(fake):
    loop_a, loop_b = asyncio.new_event_loop(), asyncio.new_event_loop()
    try:
        store = LayerStore()
        MapLibreEngine(MapWidget(), store, loop=loop_a)
        with pytest.raises(RuntimeError):
            MapLibreEngine(MapWidget(), store, loop=loop_b)
        MapLibreEngine(MapWidget(), store, loop=loop_a)
    finally:
        loop_a.close()
        loop_b.close()


@pytest.mark.asyncio
async def test_write_from_another_thread_is_handed_to_the_loop(fake, caplog):
    loop = asyncio.get_running_loop()
    widget, store, engine = on_loop()

    def writer():
        store.add(tile_spec("a"))
        store.add(tile_spec("b"))

    with caplog.at_level(logging.WARNING, logger="sepalui.mapping"):
        thread = threading.Thread(target=writer)
        thread.start()
        thread.join()
        await engine.wait_idle()
    warnings = [r for r in caplog.records if "thread" in r.getMessage()]
    assert len(warnings) == 1
    assert ids_of(widget) == ["b", "a"]
    assert {call_loop for _, call_loop in fake.calls} == {loop}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_status_follows_the_views(fake):
    widget, store, _ = headless()
    store.add(tile_spec("a"))
    assert store.view("a").status == "ready"
    open_view(widget)
    assert store.view("a").status == "pending"
    report(widget, "a", "loading")
    assert store.view("a").status == "pending"
    report(widget, "a", "ready")
    assert store.view("a").status == "ready"
    report(widget, "a", "error", error="tile 404")
    assert (store.view("a").status, store.view("a").error) == ("error", "tile 404")
    close_view(widget)
    assert (store.view("a").status, store.view("a").error) == ("ready", "")


def test_status_ignores_status_events_for_drawing(fake):
    widget, store, _ = headless()
    store.add(tile_spec("a"))
    revision = widget.state["revision"]
    store.set_status("a", "pending")
    store.set_status("a", "error", error="x")
    assert widget.state["revision"] == revision


@pytest.mark.asyncio
async def test_reserved_replacement_failing_before_commit_keeps_the_first_prepare(fake):
    widget, store, engine = on_loop()
    gate = fake.hold("a")
    store.add(tile_spec("a"))
    await wait_until(lambda: fake.calls)
    generation = store.reserve("a")  # an async writer announces a replacement...
    store.release("a", generation)  # ...and fails before committing it
    gate.set()
    await engine.wait_idle()
    assert ids_of(widget) == ["a"]
    assert store.view("a").status == "ready"


@pytest.mark.asyncio
async def test_theme_switch_during_prepare(fake):
    widget, store, engine = on_loop()
    gate = fake.hold("v")
    store.add(vector_spec("v"))
    await wait_until(lambda: fake.calls)
    engine.configure(theme="dark")
    await wait_until(lambda: widget.state.get("theme") == "dark")
    gate.set()
    await engine.wait_idle()
    paint = layer_of(widget, "v")["paint"]
    assert paint["stroke"] == paint["fill"] == THEMES[True]["primary"]


@pytest.mark.asyncio
async def test_remove_and_readd_same_spec_in_one_tick(fake):
    widget, store, engine = on_loop()
    spec = vector_spec("v")
    store.add(spec)
    await engine.wait_idle()
    open_view(widget)
    report(widget, "v", "ready")
    old = layer_of(widget, "v")
    store.remove("v")
    store.add(spec)
    await engine.wait_idle()
    new = layer_of(widget, "v")
    assert new["instance"] != old["instance"]
    report(widget, "v", "ready")
    report(widget, "v", "error", error="late", token=old["token"], instance=old["instance"])
    assert (store.view("v").status, store.view("v").error) == ("ready", "")
    open_view(widget, "fresh")
    assert pulled(widget, new["source"]["digest"]) == payload(collection(0))


def test_shared_store_status(fake):
    store, quiet, mounted = LayerStore(), MapWidget(), MapWidget()
    MapLibreEngine(quiet, store)
    shown = MapLibreEngine(mounted, store)
    store.add(tile_spec("t"))
    assert store.view("t").status == "ready"
    open_view(mounted)
    assert store.view("t").status == "pending"
    report(mounted, "t", "error", error="tile 500")
    assert (store.view("t").status, store.view("t").error) == ("error", "tile 500")
    shown.close()
    assert (store.view("t").status, store.view("t").error) == ("ready", "")
    store.set_opacity("t", 0.3)
    assert layer_of(quiet, "t")["opacity"] == 0.3


def gated_by_interface(monkeypatch, legend):
    """Patch ``prepare``: one gate per interface; "b" fails, "c" draws its own legend."""
    gates = {"a": asyncio.Event(), "b": asyncio.Event(), "c": asyncio.Event()}

    async def gated(spec, *, gee_interface=None, **kw):
        await gates[gee_interface].wait()
        if gee_interface == "b":
            raise LayerPrepareError(f"{spec.name}: b failed", layer_id=spec.id)
        own = Legend(title="C") if gee_interface == "c" else legend
        url = f"https://{gee_interface}.test/{{z}}/{{x}}/{{y}}"
        return RenderLayer(render_hash=spec.render_hash, kind="raster-xyz", url=url, legend=own)

    monkeypatch.setattr(maplibre_engine, "prepare", gated)
    return gates


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["a_first", "b_first"])
async def test_shared_store_prepare_outcomes(order, monkeypatch):
    legend = Legend(title="A")
    gates = gated_by_interface(monkeypatch, legend)
    loop, store = asyncio.get_running_loop(), LayerStore()
    a = MapLibreEngine(MapWidget(loop=loop), store, gee_interface="a", loop=loop)
    b = MapLibreEngine(MapWidget(loop=loop), store, gee_interface="b", loop=loop)
    store.add(tile_spec("t"))
    if order == "a_first":
        gates["a"].set()
        await wait_until(lambda: a.accepted("t") is not None)
        gates["b"].set()
    else:
        gates["b"].set()
        await wait_until(lambda: store.view("t").status == "error")
        gates["a"].set()
    await a.wait_idle()
    await b.wait_idle()
    view = store.view("t")
    assert (view.status, view.error) == ("error", "t: b failed")
    assert (view.legend, view.kind) == (legend, "raster-xyz")
    b.close()
    view = store.view("t")
    assert (view.status, view.error, view.legend) == ("ready", "", legend)


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["a_first", "c_first"])
async def test_shared_store_legend_comes_from_the_first_engine(order, monkeypatch):
    legend = Legend(title="A")
    gates = gated_by_interface(monkeypatch, legend)
    loop, store = asyncio.get_running_loop(), LayerStore()
    a = MapLibreEngine(MapWidget(loop=loop), store, gee_interface="a", loop=loop)
    c = MapLibreEngine(MapWidget(loop=loop), store, gee_interface="c", loop=loop)
    store.add(tile_spec("t"))
    first, second = (a, c) if order == "a_first" else (c, a)
    gates[first.gee_interface].set()
    await wait_until(lambda: first.accepted("t") is not None)
    gates[second.gee_interface].set()
    await a.wait_idle()
    await c.wait_idle()
    assert (store.view("t").status, store.view("t").legend) == ("ready", legend)
    a.close()
    assert store.view("t").legend == Legend(title="C")


@pytest.mark.asyncio
async def test_closing_the_pending_engine_settles_status(monkeypatch):
    gates = gated_by_interface(monkeypatch, None)
    loop, store = asyncio.get_running_loop(), LayerStore()
    a = MapLibreEngine(MapWidget(loop=loop), store, gee_interface="a", loop=loop)
    b = MapLibreEngine(MapWidget(loop=loop), store, gee_interface="b", loop=loop)
    store.add(tile_spec("t"))
    gates["a"].set()
    await wait_until(lambda: a.accepted("t") is not None)
    await a.wait_idle()
    assert store.view("t").status == "pending"
    b.close()
    assert store.view("t").status == "ready"
    await b.wait_idle()


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bounds_follow_the_prepare(fake):
    _, store, engine = on_loop()
    assert engine.bounds("v") == "missing"
    gate = fake.hold("v")
    store.add(vector_spec("v"))
    assert engine.bounds("v") == "preparing"
    fake.errors["bad"] = "nope"
    store.add(tile_spec("bad"))
    store.add(tile_spec("t"))
    await wait_until(lambda: store.view("bad").status == "error")
    assert engine.bounds("bad") == "failed"
    gate.set()
    await engine.wait_idle()
    assert engine.bounds("v") == (0.0, 0.0, 1.0, 1.0)
    assert await engine.bounds_async("v") == (0.0, 0.0, 1.0, 1.0)
    assert engine.bounds("t") == "no_bounds"


def ee_engine(fake, gee_spec, gee):
    _, store, engine = headless(gee_interface=gee)
    store.add(gee_spec)
    return engine


def lookup(engine, variant, layer_id="g"):
    if variant == "sync":
        return engine.bounds(layer_id)
    return asyncio.run(engine.bounds_async(layer_id))


@pytest.mark.parametrize("variant", ["sync", "async"])
def test_ee_bounds_resolved_once_and_cached(variant, fake, gee_spec):
    gee = FakeGee((10, 10, 20, 20))
    engine = ee_engine(fake, gee_spec, gee)
    assert lookup(engine, variant) == (10.0, 10.0, 20.0, 20.0)
    assert lookup(engine, variant) == (10.0, 10.0, 20.0, 20.0)
    assert gee.calls == 1


@pytest.mark.parametrize(
    "answer",
    [
        (-180, -90, 180, 90),
        ee.EEException("Image.geometry: unbounded"),
        EERestException({"code": 400, "message": "bad request"}),
    ],
)
def test_unbounded_ee_image_has_no_bounds(fake, gee_spec, answer):
    gee = FakeGee(answer)
    engine = ee_engine(fake, gee_spec, gee)
    assert engine.bounds("g") == "no_bounds"
    assert engine.bounds("g") == "no_bounds"
    assert gee.calls == 1


def test_transient_bounds_failure_is_not_cached(fake, gee_spec):
    gee = FakeGee(ConnectionError("network down"), (1, 2, 3, 4))
    engine = ee_engine(fake, gee_spec, gee)
    assert engine.bounds("g") == "failed"
    assert engine.bounds("g") == (1.0, 2.0, 3.0, 4.0)
    assert gee.calls == 2


@pytest.mark.parametrize("code", [401, 403, 429, 503])
def test_quota_error_is_not_no_bounds(fake, gee_spec, code):
    gee = FakeGee(EERestException({"code": code, "message": "quota"}), (1, 2, 3, 4))
    engine = ee_engine(fake, gee_spec, gee)
    assert engine.bounds("g") == "failed"
    assert engine.bounds("g") == (1.0, 2.0, 3.0, 4.0)


# ---------------------------------------------------------------------------
# Point layers
# ---------------------------------------------------------------------------


def with_style(spec: LayerSpec, **style) -> LayerSpec:
    return spec.revise(style=VectorStyle(**style))


def test_point_style_maps_to_widget_layer(fake):
    widget, store, _ = headless()
    style = {"marker": "pin", "radius": 7, "cluster": True, "cluster_radius": 40}
    store.add(with_style(vector_spec("p"), **style, cluster_max_zoom=12, popup=True, tooltip=["a"]))
    x = layer_of(widget, "p")
    assert x["paint"]["marker"] == "pin"
    assert x["paint"]["point_radius"] == 7
    assert x["source"]["cluster"] == {"radius": 40, "max_zoom": 12}
    assert x["interaction"] == {"popup": [], "tooltip": ["a"]}


def test_default_point_style_has_no_cluster(fake):
    widget, store, _ = headless()
    store.add(vector_spec("p"))
    x = layer_of(widget, "p")
    assert x["paint"]["marker"] == "circle"
    assert not x["source"].get("cluster")


def test_class_colors_reach_the_widget_paint(fake):
    widget, store, _ = headless()
    style = VectorStyle(color_by="status", class_colors={"a": "#ff0000", "b": "#00ff00"})
    spec = LayerSpec.from_points([(0.0, 0.0)], name="p", id="p", style=style)
    fake.data[spec.source.uri] = collection(0)
    store.add(spec)
    primary = THEMES[False]["primary"]
    assert layer_of(widget, "p")["paint"] == {
        "stroke": primary,
        "fill": primary,
        "fill_opacity": 1.0,
        "width": 2.0,
        "point_radius": 5.0,
        "marker": "circle",
        "color_by": "status",
        "class_colors": [["a", "#ff0000"], ["b", "#00ff00"]],
    }


def test_pmtiles_cluster_is_layer_error(fake):
    widget, store, _ = headless()
    spec = LayerSpec.from_vector("https://x.org/a.pmtiles", id="pm", layer="roads", name="pm")
    store.add(with_style(spec, cluster=True))
    view = store.view("pm")
    assert view.status == "error"
    assert "PMTiles cannot be clustered" in view.error
    assert ids_of(widget) == []


def test_cluster_with_polygons_is_layer_error(fake):
    widget, store, _ = headless()
    polygon = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
    }
    fake.data["https://data.test/a.geojson"] = {"type": "FeatureCollection", "features": [polygon]}
    store.add(with_style(vector_spec("a"), cluster=True))
    view = store.view("a")
    assert (view.status, view.error) == ("error", "clustering needs point features only")
    assert ids_of(widget) == []


@pytest.mark.parametrize(
    "name", ["cluster", "cluster_id", "point_count", "point_count_abbreviated"]
)
def test_cluster_reserved_property_is_layer_error(fake, name):
    widget, store, _ = headless()
    feature = collection(0)["features"][0] | {"properties": {name: 1}}
    fake.data["https://data.test/a.geojson"] = {"type": "FeatureCollection", "features": [feature]}
    store.add(with_style(vector_spec("a"), cluster=True))
    view = store.view("a")
    assert (view.status, view.error) == ("error", f"property {name} is reserved for clusters")
    assert ids_of(widget) == []


def test_restyle_cluster_reuses_payload_new_instance(fake):
    widget, store, _ = headless()
    store.add(vector_spec("p"))
    before = layer_of(widget, "p")
    store.restyle("p", cluster=True)
    after = layer_of(widget, "p")
    assert after["source"]["digest"] == before["source"]["digest"]
    assert after["source"]["cluster"] == {"radius": 50, "max_zoom": 14}
    assert after["instance"] != before["instance"]
    assert fake.calls == [("p", None)]


def test_popup_restyle_keeps_instance(fake):
    widget, store, _ = headless()
    store.add(vector_spec("p"))
    before = layer_of(widget, "p")
    store.restyle("p", popup=True, marker="pin")
    after = layer_of(widget, "p")
    assert after["instance"] == before["instance"]
    assert after["interaction"]["popup"] == []
    assert fake.calls == [("p", None)]


class CountingGee:
    """Counts map id requests."""

    def __init__(self) -> None:
        """Start with no requests."""
        self.calls = 0

    def get_map_id(self, image, params):
        self.calls += 1
        url = f"https://ee.test/{self.calls}/{{z}}/{{x}}/{{y}}"
        return {"tile_fetcher": type("F", (), {"url_format": url})()}


def test_ee_vector_point_restyle_reuses_render(monkeypatch):
    import pysepal.layers.preparation as preparation
    import pysepal.mapping.visualization as visualization
    from pysepal.layers import GeeSource

    monkeypatch.setattr(GeeSource, "to_ee", lambda self: object())
    monkeypatch.setattr(
        visualization, "process_vis_params", lambda obj, vis_params, **kw: (obj, obj, vis_params)
    )
    monkeypatch.setattr(preparation, "theme_vis_params", lambda obj, params: None)
    gee = CountingGee()
    widget, store, _ = headless(gee_interface=gee)
    store.add(
        LayerSpec(
            id="g",
            name="g",
            source=GeeSource(expr={}, kind="FeatureCollection"),
            style=VectorStyle(stroke="#112233"),
        )
    )
    assert gee.calls == 1
    before = layer_of(widget, "g")
    store.restyle("g", popup=True)
    store.restyle("g", marker="pin", radius=8)
    assert gee.calls == 1
    assert layer_of(widget, "g")["instance"] == before["instance"]
    store.restyle("g", stroke="#ff0000")
    assert gee.calls == 2


def test_accepted_instance_follows_the_published_instance(fake):
    widget, store, engine = headless()
    assert engine.accepted_instance("a") is None
    store.add(vector_spec("a"))
    assert engine.accepted_instance("a") == layer_of(widget, "a")["instance"]
    before = engine.accepted_instance("a")
    store.add(tile_spec("a"), replace=True)
    assert engine.accepted_instance("a") == layer_of(widget, "a")["instance"]
    assert engine.accepted_instance("a") != before


@pytest.mark.asyncio
async def test_side_reaches_widget_state_and_keeps_instance(fake):
    widget, store, engine = on_loop()
    store.add(tile_spec("a"), side="left")
    await engine.wait_idle()
    open_view(widget)
    report(widget, "a", "ready")
    before = layer_of(widget, "a")
    assert before["side"] == "left"
    revision = widget.state["revision"]
    store.set_side("a", "right")
    await engine.wait_idle()
    after = layer_of(widget, "a")
    assert widget.state["revision"] == revision + 1
    assert after["side"] == "right"
    assert after["instance"] == before["instance"]


@pytest.mark.asyncio
async def test_compare_reaches_widget_state(fake):
    widget, _, engine = on_loop()
    await engine.wait_idle()
    assert widget.state["compare"] is False
    engine.configure(compare=True)
    await engine.wait_idle()
    assert widget.state["compare"] is True
    engine.configure(theme="dark")
    await engine.wait_idle()
    assert widget.state["compare"] is True


def test_configure_rejects_non_bool_compare(fake):
    _, _, engine = headless()
    for value in (1, "yes", None):
        with pytest.raises(TypeError):
            engine.configure(compare=value)

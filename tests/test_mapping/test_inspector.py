"""Tests of the map inspector, on a made-up map: published state, engine and Earth Engine."""

import asyncio
import os
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pysepal_map import ClickEvent, FeatureHit
from rasterio.transform import from_origin
from rasterio.warp import transform as warp_transform

from pysepal.layers import (
    GeeSource,
    LayerSpec,
    RasterStyle,
    RenderLayer,
    VectorStyle,
    local_fingerprint,
)
from pysepal.mapping import SepalMap
from pysepal.mapping.inspector import (
    InspectedLayer,
    Inspection,
    MapInspector,
    inspect_point,
)

# ---------------------------------------------------------------------------
# A made-up map and Earth Engine
# ---------------------------------------------------------------------------


class FakeEE:
    """An Earth Engine object that records the scale and answers with ``answer``.

    An answer that is a future is awaited by the fake interface, an exception is raised.
    """

    def __init__(self, answer=None, scales=None) -> None:
        """Answer with ``answer`` and record scales in ``scales``."""
        self.answer, self.scales = answer, scales if scales is not None else []
        self.queue: list = []

    def reduceRegion(self, reducer, geometry, scale):
        self.scales.append(scale)
        return FakeEE(self.queue.pop(0) if self.queue else self.answer, self.scales)

    def filterBounds(self, geometry):
        return FakeEE(self.answer, self.scales)

    def limit(self, count):
        return self


class FakeGee:
    async def get_info_async(self, obj):
        answer = obj.answer
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, asyncio.Future):
            return await answer
        return answer


class FakeEngine:
    def __init__(self) -> None:
        """Start with no accepted layers."""
        self.entries: dict[str, tuple[LayerSpec, RenderLayer, int | None]] = {}

    def accepted(self, layer_id):
        entry = self.entries.get(layer_id)
        return None if entry is None else entry[:2]

    def accepted_instance(self, layer_id):
        entry = self.entries.get(layer_id)
        return None if entry is None else entry[2]


class FakeMap:
    def __init__(self) -> None:
        """Start empty, with no click callback."""
        self.state = {"layers": ()}
        self.layer_engine = FakeEngine()
        self.gee_interface = FakeGee()
        self.view = None
        self.cursor = ""
        self.marker = None
        self.callbacks: list = []
        self._instances = 0

    @property
    def loop(self):
        return asyncio.get_running_loop()

    def on_click(self, callback, remove=False):
        if remove:
            self.callbacks.remove(callback)
        elif callback not in self.callbacks:
            self.callbacks.append(callback)

    def set_marker(self, lng, lat, color="#3388ff"):
        self.marker = (lng, lat)

    def clear_marker(self):
        self.marker = None

    def click(self, event):
        for callback in list(self.callbacks):
            callback(event)

    def add(self, spec, render, *, visible=True, published=True, instance=None):
        """Accept a layer and, unless ``published`` is False, publish it below the others."""
        self._instances += 1
        instance = self._instances if instance is None else instance
        self.layer_engine.entries[spec.id] = (spec, render, instance)
        if published:
            entry = {
                "id": spec.id,
                "instance": instance,
                "zone": spec.zone,
                "visible": visible,
                "kind": render.kind,
            }
            self.state = {"layers": (*self.state["layers"], entry)}
        return instance

    def accept_replacement(self, layer_id):
        spec, render, _ = self.layer_engine.entries[layer_id]
        self._instances += 1
        self.layer_engine.entries[layer_id] = (spec, render, self._instances)


def click(lng=0.5, lat=0.5, zoom=5, settled=True, features=(), stale=()) -> ClickEvent:
    return ClickEvent(lng, lat, zoom, settled, tuple(features), frozenset(stale), "a")


def ee_layer(m, layer_id, answer, kind="Image", **kw) -> FakeEE:
    style = RasterStyle() if kind == "Image" else VectorStyle()
    zone = kw.pop("zone", "data")
    spec = LayerSpec(
        id=layer_id,
        name=f"name {layer_id}",
        source=GeeSource(expr={}, kind=kind),
        style=style,
        zone=zone,
    )
    obj = FakeEE(answer)
    m.add(spec, RenderLayer(render_hash=spec.render_hash, kind="raster-xyz", ee_object=obj), **kw)
    return obj


def vector_layer(m, layer_id, kind="geojson", **kw) -> int:
    spec = LayerSpec.from_vector(
        f"https://data.test/{layer_id}.geojson", name=layer_id, id=layer_id
    )
    return m.add(spec, RenderLayer(render_hash=spec.render_hash, kind=kind), **kw)


def raster_layer(m, path: Path, layer_id="r", **kw) -> LayerSpec:
    spec = LayerSpec.from_raster(path, name=layer_id, id=layer_id)
    render = RenderLayer(
        render_hash=spec.render_hash,
        kind="raster-xyz",
        raster=str(path),
        fingerprint=local_fingerprint(spec),
    )
    m.add(spec, render, **kw)
    return spec


async def settle(times: int = 30) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


def by_id(layers):
    return {x.layer_id: x for x in layers}


@pytest.fixture
def amap() -> FakeMap:
    return FakeMap()


def write_raster(path: Path, data, nodata=None, descriptions=None) -> Path:
    data = np.asarray(data, dtype="uint8")
    if data.ndim == 2:
        data = data[None]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(10, 20, 1, 1),
        nodata=nodata,
    ) as ds:
        ds.write(data)
        if descriptions:
            ds.descriptions = descriptions
    return path


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rows_follow_published_order_and_visibility(amap):
    ee_layer(amap, "b", {"x": 1.0})
    ee_layer(amap, "hidden", {"x": 2.0}, visible=False)
    ee_layer(amap, "overlay", {"x": 3.0}, zone="overlay")
    ee_layer(amap, "a", {"x": 4.0})
    layers = await inspect_point(amap, click())
    assert [x.layer_id for x in layers] == ["b", "a"]
    assert [x.name for x in layers] == ["name b", "name a"]
    assert layers[0].values == (("x", "1"),)


@pytest.mark.asyncio
async def test_scale_comes_from_click_zoom(amap):
    obj = ee_layer(amap, "a", {"x": 1.0})
    amap.view = {"center": [0, 0], "zoom": 1}
    await inspect_point(amap, click(lat=60, zoom=4))
    await inspect_point(amap, click(lat=0, zoom=12))
    assert obj.scales == [
        pytest.approx(78271.517 * 0.5 / 2**4),
        pytest.approx(78271.517 / 2**12),
    ]


@pytest.mark.asyncio
async def test_ee_values_are_formatted(amap):
    ee_layer(amap, "a", {"b1": 1.23456789, "b2": 2.0, "b3": None, "b4": 7})
    [layer] = await inspect_point(amap, click())
    assert layer.status == "ready"
    assert layer.values == (("b1", "1.2346"), ("b2", "2"), ("b3", "nodata"), ("b4", "7"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind, answer, status, values",
    [
        ("Geometry", {"features": [{"properties": {"n": 5}}]}, "ready", (("n", "5"),)),
        ("Feature", {"features": [{"properties": {"n": "x"}}]}, "ready", (("n", "x"),)),
        ("FeatureCollection", {"features": [{"properties": {"a": 0.5}}]}, "ready", (("a", "0.5"),)),
        ("FeatureCollection", {"features": []}, "empty", ()),
    ],
)
async def test_ee_vector_kinds(amap, kind, answer, status, values):
    ee_layer(amap, "v", answer, kind=kind)
    [layer] = await inspect_point(amap, click())
    assert (layer.status, layer.values) == (status, values)


@pytest.mark.asyncio
async def test_one_layer_error_is_isolated(amap):
    ee_layer(amap, "bad", RuntimeError("boom"))
    ee_layer(amap, "good", {"x": 1.0})
    layers = by_id(await inspect_point(amap, click()))
    assert layers["bad"].status == "error" and "boom" in layers["bad"].error
    assert layers["good"].status == "ready"


# ---------------------------------------------------------------------------
# Local rasters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_raster_values(amap, byte, raster_spec):
    render = RenderLayer(
        render_hash=raster_spec.render_hash,
        kind="raster-xyz",
        raster=str(byte),
        fingerprint=local_fingerprint(raster_spec),
    )
    amap.add(raster_spec, render)
    with rasterio.open(byte) as ds:
        x, y = ds.xy(ds.height // 2, ds.width // 2)
        [lng], [lat] = warp_transform(ds.crs, "EPSG:4326", [x], [y])
        expected = ds.read(1)[ds.height // 2, ds.width // 2]
    [inside] = await inspect_point(amap, click(lng, lat))
    assert inside.status == "ready" and inside.values == (("band 1", str(int(expected))),)
    [outside] = await inspect_point(amap, click(0, 0))
    assert outside.status == "empty"


@pytest.mark.asyncio
async def test_local_raster_nodata_and_band_labels(amap, tmp_path):
    path = write_raster(
        tmp_path / "r.tif",
        [[[1, 0], [3, 4]], [[5, 6], [7, 8]]],
        nodata=0,
        descriptions=("foo", None),
    )
    raster_layer(amap, path)
    [first] = await inspect_point(amap, click(10.5, 19.5))
    assert first.values == (("foo", "1"), ("band 2", "5"))
    [second] = await inspect_point(amap, click(11.5, 19.5))
    assert second.values == (("foo", "nodata"), ("band 2", "6"))


@pytest.mark.asyncio
async def test_raster_replaced_on_disk_is_changed(amap, tmp_path):
    path = write_raster(tmp_path / "r.tif", [[1, 2], [3, 4]])
    raster_layer(amap, path)
    write_raster(path, [[9, 9], [9, 9]])
    later = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))
    [layer] = await inspect_point(amap, click(10.5, 19.5))
    assert layer.status == "changed" and layer.values == ()


# ---------------------------------------------------------------------------
# Vectors and tiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["geojson", "pmtiles"])
async def test_vector_values_from_hits(amap, kind):
    instance = vector_layer(amap, "v", kind=kind)
    vector_layer(amap, "none", kind=kind)
    props = {"a": 1.23456789, "b": {"x": 1}, "c": "s"}
    hit = FeatureHit("v", instance, props)
    layers = by_id(await inspect_point(amap, click(features=[hit])))
    assert layers["v"].status == "ready"
    assert layers["v"].values == (("a", "1.2346"), ("b", '{"x": 1}'), ("c", "s"))
    assert layers["none"].status == "empty"


@pytest.mark.asyncio
async def test_tile_layer_unsupported(amap):
    spec = LayerSpec.from_tiles("https://t.test/{z}/{x}/{y}.png", name="t", id="t")
    amap.add(spec, RenderLayer(render_hash=spec.render_hash, kind="raster-xyz"))
    [layer] = await inspect_point(amap, click())
    assert layer.status == "unsupported"


@pytest.mark.asyncio
async def test_stale_hit_row_is_changed(amap):
    vector_layer(amap, "v")
    [layer] = await inspect_point(amap, click(stale=["v"]))
    assert layer.status == "changed"


@pytest.mark.asyncio
async def test_hit_on_another_instance_is_changed(amap):
    instance = vector_layer(amap, "v")
    hit = FeatureHit("v", instance + 100, {"a": 1})
    [layer] = await inspect_point(amap, click(features=[hit]))
    assert layer.status == "changed" and layer.values == ()


@pytest.mark.asyncio
async def test_unsettled_click_without_hit_is_changed(amap):
    vector_layer(amap, "v")
    [layer] = await inspect_point(amap, click(settled=False))
    assert layer.status == "changed"


@pytest.mark.asyncio
async def test_replacement_accepted_before_click_published_after(amap):
    ee_layer(amap, "a", {"x": 1.0})
    ee_layer(amap, "b", {"x": 2.0})
    amap.accept_replacement("a")
    layers = by_id(await inspect_point(amap, click()))
    assert layers["a"].status == "changed"
    assert layers["b"].status == "ready" and layers["b"].values == (("x", "2"),)


# ---------------------------------------------------------------------------
# The inspector
# ---------------------------------------------------------------------------


def started(amap) -> MapInspector:
    inspector = MapInspector(amap)
    inspector.activate()
    return inspector


@pytest.mark.asyncio
async def test_activate_and_deactivate_own_cursor_and_callback(amap):
    inspector = started(amap)
    assert inspector.active and amap.cursor == "crosshair" and len(amap.callbacks) == 1
    amap.click(click())
    assert amap.marker == (0.5, 0.5)
    assert inspector.inspection.pending and inspector.inspection.layers == ()
    inspector.deactivate()
    assert not inspector.active and amap.callbacks == []
    assert amap.cursor == "" and amap.marker is None and inspector.inspection is None


@pytest.mark.asyncio
async def test_click_applies_the_result(amap):
    ee_layer(amap, "a", {"x": 1.0})
    inspector = started(amap)
    amap.click(click(lng=3, lat=4, zoom=2))
    await settle()
    inspection = inspector.inspection
    assert isinstance(inspection, Inspection) and not inspection.pending
    assert (inspection.lng, inspection.lat) == (3, 4)
    assert inspection.scale == pytest.approx(78271.517 * np.cos(np.radians(4)) / 4)
    assert inspection.layers[0].values == (("x", "1"),)


@pytest.mark.asyncio
async def test_newer_click_supersedes_older(amap):
    loop = asyncio.get_running_loop()
    first, second = loop.create_future(), loop.create_future()
    obj = ee_layer(amap, "a", None)
    obj.queue = [first, second]
    inspector = started(amap)
    amap.click(click(lng=1))
    await settle()
    amap.click(click(lng=2))
    await settle()
    second.set_result({"x": 2.0})
    await settle()
    if not first.done():
        first.set_result({"x": 1.0})
    await settle()
    assert inspector.inspection.lng == 2 and not inspector.inspection.pending
    assert inspector.inspection.layers[0].values == (("x", "2"),)


@pytest.mark.asyncio
async def test_deactivate_drops_late_result(amap):
    loop = asyncio.get_running_loop()
    answer = loop.create_future()
    ee_layer(amap, "a", answer)
    inspector = started(amap)
    amap.click(click())
    await settle()
    inspector.deactivate()
    if not answer.done():
        answer.set_result({"x": 1.0})
    await settle()
    assert inspector.inspection is None and amap.marker is None and amap.cursor == ""


def late_inspections(monkeypatch) -> list:
    """Replace ``inspect_point`` by one that ignores cancellation and answers when released.

    Returns the futures, one per call, each resolved with the layers to answer.
    """
    futures: list = []

    async def late(map_, event, rows=None):
        future = asyncio.get_running_loop().create_future()
        futures.append(future)
        while True:
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                continue  # the result still arrives after the click was superseded

    monkeypatch.setattr("pysepal.mapping.inspector.inspect_point", late)
    return futures


def answer_of(value: str) -> list:
    return [InspectedLayer("a", "a", "ready", (("x", value),))]


@pytest.mark.asyncio
async def test_superseded_late_result_is_dropped(amap, monkeypatch):
    futures = late_inspections(monkeypatch)
    inspector = started(amap)
    amap.click(click(lng=1))
    await settle()
    amap.click(click(lng=2))
    await settle()
    futures[1].set_result(answer_of("2"))
    await settle()
    futures[0].set_result(answer_of("1"))
    await settle()
    assert inspector.inspection.lng == 2 and not inspector.inspection.pending
    assert inspector.inspection.layers[0].values == (("x", "2"),)


@pytest.mark.asyncio
async def test_deactivated_late_result_is_dropped(amap, monkeypatch):
    futures = late_inspections(monkeypatch)
    inspector = started(amap)
    amap.click(click())
    await settle()
    inspector.deactivate()
    futures[0].set_result(answer_of("1"))
    await settle()
    assert inspector.inspection is None and amap.marker is None and amap.cursor == ""


@pytest.mark.asyncio
async def test_click_pairs_before_the_task_runs(amap):
    ee_layer(amap, "a", {"x": 1.0})
    inspector = started(amap)
    amap.click(click())
    amap.accept_replacement("a")  # accepted after the click, before the task's first step
    await settle()
    # paired at the click, the row reads the clicked instance; pairing in the task would say "changed"
    assert [x.status for x in inspector.inspection.layers] == ["ready"]


def test_sepal_map_builds_and_closes_the_inspector():
    assert SepalMap(gee=False).inspector is None
    m = SepalMap(gee=False, inspector=True)
    assert isinstance(m.inspector, MapInspector)
    m.inspector.activate()
    m.close()
    assert not m.inspector.active

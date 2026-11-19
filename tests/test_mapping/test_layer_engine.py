"""Tests of the engine mirroring a LayerStore onto an ipyleaflet map."""

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

import ipyleaflet as ipl
import pytest
import rasterio

import pysepal.layers.preparation as preparation
import pysepal.mapping.layer_engine as layer_engine
from pysepal.layers import (
    LayerPrepareError,
    LayerSpec,
    LayerStore,
    RenderLayer,
    prepare_sync,
)
from pysepal.mapping.inspector_control import InspectorControl
from pysepal.mapping.layer import EELayer
from pysepal.mapping.layer_engine import (
    OVERLAY_PANE,
    PANE_PREFIX,
    LeafletEngine,
    PanedGeoJSON,
    pane_name,
)
from pysepal.mapping.sepal_map import SepalMap
from tests.test_solara._harness import wait_until


def write_point(path: Path, x: float) -> None:
    """Write a one-point FeatureCollection at ``[x, 0]`` with a later mtime than before."""
    before = path.stat().st_mtime_ns if path.exists() else time.time_ns()
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Point", "coordinates": [x, 0]},
    }
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))
    # a second forward, so the fingerprint changes even on coarse filesystem clocks
    later = max(path.stat().st_mtime_ns, before) + 1_000_000_000
    os.utime(path, ns=(later, later))


def first_coords(layer: ipl.GeoJSON) -> list:
    """Return the coordinates of the first feature of a GeoJSON layer."""
    return layer.data["features"][0]["geometry"]["coordinates"]


def test_panes_created():
    m = ipl.Map()
    LeafletEngine(m, LayerStore())
    assert m.panes["pysepal-layer-398"] == {"zIndex": "398"}
    assert m.panes[OVERLAY_PANE] == {"zIndex": "399"}
    assert len([p for p in m.panes if p.startswith(PANE_PREFIX)]) == 198


def test_panes_are_numbered_from_the_bottom():
    assert [pane_name(slot, 3) for slot in range(3)] == [
        "pysepal-layer-203",
        "pysepal-layer-202",
        "pysepal-layer-201",
    ]
    # past the last pane, the lowest layers share it and the top ones keep theirs
    assert pane_name(0, 200) == "pysepal-layer-398"
    assert pane_name(197, 200) == pane_name(199, 200) == "pysepal-layer-201"


def test_add_attaches_in_bottom_pane(raster_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    layer = engine.leaflet_layer(raster_spec.id)
    assert layer in m.layers
    assert layer.pane == "pysepal-layer-201"
    assert store.view(raster_spec.id).status == "ready"


def test_move_repanes_only_changed(raster_spec, vector_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    store.add(vector_spec)  # vector on top
    store.move(raster_spec.id, 0)
    assert engine.leaflet_layer(raster_spec.id).pane == "pysepal-layer-202"
    assert engine.leaflet_layer(vector_spec.id).pane == "pysepal-layer-201"


def test_vector_can_sit_below_raster(raster_spec, vector_spec):
    # the pane z-index, not the layer type, decides the stacking
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(vector_spec)
    store.add(raster_spec)
    assert engine.leaflet_layer(raster_spec.id).pane > engine.leaflet_layer(vector_spec.id).pane


def test_hide_pmtiles_detaches_and_keeps_pane(pmtiles_spec, raster_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    store.add(pmtiles_spec)
    layer = engine.leaflet_layer(pmtiles_spec.id)
    store.set_visible(pmtiles_spec.id, False)
    assert layer not in m.layers
    store.set_visible(pmtiles_spec.id, True)
    assert engine.leaflet_layer(pmtiles_spec.id) in m.layers
    assert engine.leaflet_layer(pmtiles_spec.id).pane == "pysepal-layer-202"


def test_geojson_pane_is_a_creation_option(vector_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(vector_spec)
    layer = engine.leaflet_layer(vector_spec.id)
    assert isinstance(layer, PanedGeoJSON)
    assert "pane" in layer.options
    assert layer.point_style["pane"] == layer.pane


def test_local_raster_is_bound_tile_layer(raster_spec, monkeypatch):
    m = SepalMap(gee=False)
    store = LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    layer = engine.leaflet_layer(raster_spec.id)
    assert type(layer).__name__ == "BoundTileLayer"
    assert layer.tile_server is not None and layer.raster
    seen = []
    monkeypatch.setattr(InspectorControl, "_from_raster", lambda self, r, c: seen.append(r) or {})
    m.v_inspector.menu.v_model = True  # read_data returns early on an inactive inspector
    m.v_inspector.read_data(type="click", coordinates=[0, 0])
    assert seen == [layer.raster]


def test_switching_source_type_replaces_widget(raster_spec, gee_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    before = engine.leaflet_layer(raster_spec.id)
    swapped = gee_spec.model_copy(update={"id": raster_spec.id})
    engine.put(
        RenderLayer(render_hash=swapped.render_hash, kind="raster-xyz", url="https://t/{z}/{x}/{y}")
    )
    store.add(swapped, replace=True)
    assert engine.leaflet_layer(raster_spec.id) is not before
    assert isinstance(engine.leaflet_layer(raster_spec.id), EELayer)


def test_cache_hit_binds_current_metadata(raster_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    a = raster_spec.model_copy(update={"id": "a", "attribution": "A"})
    b = raster_spec.model_copy(update={"id": "b", "attribution": "B"})
    store.add(a)
    store.add(b)  # same render_hash: the second is a cache hit
    attributions = (engine.leaflet_layer("a").attribution, engine.leaflet_layer("b").attribution)
    assert attributions == ("A", "B")


def test_add_on_top_keeps_existing_panes(raster_spec, vector_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(vector_spec)
    store.add(raster_spec)  # raster lands at index 0
    v = engine.leaflet_layer(vector_spec.id)
    assert v.pane == "pysepal-layer-201"
    assert engine.leaflet_layer(raster_spec.id).pane == "pysepal-layer-202"
    assert v.point_style["pane"] == v.pane


def test_add_on_top_changes_the_map_once(raster_spec, vector_spec, pmtiles_spec, byte):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    for spec in (raster_spec, vector_spec, pmtiles_spec):
        store.add(spec)
    changes = []
    m.observe(lambda c: changes.append((c["old"], c["new"])), "layers")
    fourth = LayerSpec.from_raster(byte, name="d")
    store.add(fourth)
    assert len(changes) == 1
    old, new = changes[0]
    assert list(new) == [*old, engine.leaflet_layer(fourth.id)]


def test_remove_all_changes_the_map_once_per_layer(raster_spec, vector_spec, pmtiles_spec):
    m = SepalMap(gee=False)
    specs = (raster_spec, vector_spec, pmtiles_spec)
    for spec in specs:
        m.layer_store.add(spec)
    managed = {m.layer_engine.leaflet_layer(spec.id) for spec in specs}
    changes = []
    m.observe(lambda c: changes.append(set(c["old"]) ^ set(c["new"])), "layers")
    m.remove_all()
    # the map's own non-base layers (the inspector marker) go too, one change each
    touching = [diff for diff in changes if diff & managed]
    assert len(touching) == 3 and set().union(*touching) == managed


def test_remove_middle_moves_the_layers_above_down(raster_spec, raster_spec_b, vector_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(vector_spec)
    store.add(raster_spec_b)
    store.add(raster_spec)
    store.remove(raster_spec_b.id)
    assert engine.leaflet_layer(vector_spec.id).pane == "pysepal-layer-201"
    assert engine.leaflet_layer(raster_spec.id).pane == "pysepal-layer-202"


def test_hidden_vector_is_detached_and_repaned(raster_spec, vector_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    store.add(vector_spec, visible=False)
    assert engine.leaflet_layer(vector_spec.id) not in m.layers
    store.move(vector_spec.id, 1)
    store.set_visible(vector_spec.id, True)
    v = engine.leaflet_layer(vector_spec.id)
    assert v in m.layers
    assert v.pane == "pysepal-layer-201"
    assert v.point_style["pane"] == v.pane


def test_vector_restyle_updates_geojson_in_place(vector_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(vector_spec)
    layer = engine.leaflet_layer(vector_spec.id)
    store.restyle(vector_spec.id, stroke="#ff0000", width=4)
    assert engine.leaflet_layer(vector_spec.id) is layer
    assert (layer.style["color"], layer.style["weight"]) == ("#ff0000", 4)
    assert layer.point_style["color"] == "#ff0000"
    assert layer.point_style["pane"] == layer.pane


def test_vector_restyle_reads_the_file_once(vector_spec, monkeypatch):
    reads, real = [], preparation._read_vector
    monkeypatch.setattr(preparation, "_read_vector", lambda src: reads.append(src) or real(src))
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(vector_spec)
    layer = engine.leaflet_layer(vector_spec.id)
    for color in ("#ff0000", "#00ff00", "#0000ff"):
        store.restyle(vector_spec.id, stroke=color)
        assert layer.style["color"] == color
    assert len(reads) == 1
    assert engine.leaflet_layer(vector_spec.id) is layer
    geojson = [r for r in engine._cache.values() if r.kind == "geojson"]
    assert len({id(r.data) for r in geojson}) == 1


def test_vector_restyle_after_a_rewrite_reads_the_new_file(tmp_path):
    path = tmp_path / "v.geojson"
    write_point(path, 0)
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(LayerSpec.from_vector(path, id="v"))
    write_point(path, 10)
    store.restyle("v", stroke="#ff0000")
    assert first_coords(engine.leaflet_layer("v")) == [10, 0]
    assert engine.leaflet_layer("v").style["color"] == "#ff0000"


def test_inherited_fill_follows_theme(vector_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(vector_spec)
    theme_style = engine.leaflet_layer(vector_spec.id).theme_style
    assert all(set(v) == {"color", "fillColor"} for v in theme_style.values())


def test_pmtiles_restyle_rebuilds(pmtiles_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(pmtiles_spec)
    before = engine.leaflet_layer(pmtiles_spec.id)
    store.restyle(pmtiles_spec.id, stroke="#ff0000")
    after = engine.leaflet_layer(pmtiles_spec.id)
    assert after is not before
    assert after.pane == before.pane
    assert after in m.layers and before not in m.layers


def test_same_path_new_content_is_reprepared(tmp_path, byte):
    path = tmp_path / "r.tif"
    shutil.copy(byte, path)
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    spec = LayerSpec.from_raster(path, id="r")
    store.add(spec)
    first = engine.leaflet_layer("r").tile_server
    with rasterio.open(byte) as src:
        profile, data = src.profile, src.read()
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(255 - data)
    store.add(spec, replace=True)  # same spec, same render_hash
    assert engine.leaflet_layer("r").tile_server is not first


def test_same_path_vector_rewrite_replaces_features(tmp_path):
    path = tmp_path / "v.geojson"
    write_point(path, 0)
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    spec = LayerSpec.from_vector(path, id="v")
    store.add(spec)
    write_point(path, 10)
    store.add(spec, replace=True)
    assert first_coords(engine.leaflet_layer("v")) == [10, 0]
    assert engine.leaflet_layer("v") in m.layers


@pytest.mark.parametrize("older_fails", [False, True])
def test_older_prepare_finishing_last_is_dropped(tmp_path, monkeypatch, older_fails):
    path = tmp_path / "v.geojson"
    write_point(path, 0)
    gates = []

    async def gated(spec, **kw):
        render, gate = prepare_sync(spec, **kw), asyncio.Event()  # read the file now, publish later
        gates.append(gate)
        fail = older_fails and len(gates) == 1
        await gate.wait()
        if fail:
            raise LayerPrepareError(f"{spec.name}: old", layer_id=spec.id)
        return render

    monkeypatch.setattr(layer_engine, "prepare", gated)

    async def run():
        m, store = ipl.Map(), LayerStore()
        engine = LeafletEngine(m, store)
        spec = LayerSpec.from_vector(path, id="v")
        store.add(spec)
        await wait_until(lambda: len(gates) == 1)
        write_point(path, 10)
        store.add(spec, replace=True)
        await wait_until(lambda: len(gates) == 2)
        gates[1].set()
        await wait_until(lambda: store.view("v").status == "ready")
        gates[0].set()
        await engine.wait_idle()
        assert store.view("v").status == "ready"
        assert first_coords(engine.leaflet_layer("v")) == [10, 0]

    asyncio.run(run())


def test_deleted_file_reports_error(tmp_path, byte):
    path = tmp_path / "r.tif"
    shutil.copy(byte, path)
    m, store = ipl.Map(), LayerStore()
    LeafletEngine(m, store)
    spec = LayerSpec.from_raster(path, id="r")
    store.add(spec)
    path.unlink()
    store.add(spec, replace=True)
    assert store.view("r").status == "error"
    assert "r.tif" in store.view("r").error


def test_restyle_updates_url_in_place(raster_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    before = engine.leaflet_layer(raster_spec.id)
    old_url = before.url
    store.restyle(raster_spec.id, colormap="magma")
    assert engine.leaflet_layer(raster_spec.id) is before
    assert before.url != old_url


def test_stale_render_is_dropped(raster_spec):
    async def run():
        m, store = ipl.Map(), LayerStore()
        engine = LeafletEngine(m, store)
        store.add(raster_spec)
        store.restyle(raster_spec.id, colormap="magma")
        store.restyle(raster_spec.id, colormap="gray")
        await engine.wait_idle()
        assert "gray" in engine.leaflet_layer(raster_spec.id).url

    asyncio.run(run())


def test_remove_during_prepare(raster_spec):
    async def run():
        m, store = ipl.Map(), LayerStore()
        engine = LeafletEngine(m, store)
        store.add(raster_spec)
        store.remove(raster_spec.id)
        await engine.wait_idle()
        assert engine.leaflet_layer(raster_spec.id) is None
        assert not any(getattr(lyr, "layer_id", None) for lyr in m.layers)

    asyncio.run(run())


def test_prepare_error_sets_status(tmp_path, raster_spec):
    m, store = ipl.Map(), LayerStore()
    LeafletEngine(m, store)
    bad = LayerSpec.from_raster(tmp_path / "gone.tif")
    store.add(raster_spec)
    store.add(bad)
    assert store.view(bad.id).status == "error"
    assert "gone.tif" in store.view(bad.id).error
    assert store.view(raster_spec.id).status == "ready"


def _failing_build(*args, **kwargs):
    raise RuntimeError("cannot build")


def test_build_failure_sets_error(raster_spec, monkeypatch):
    monkeypatch.setattr(LeafletEngine, "_build", _failing_build)
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    assert store.view(raster_spec.id).status == "error"
    assert "cannot build" in store.view(raster_spec.id).error
    assert engine.leaflet_layer(raster_spec.id) is None
    assert raster_spec.id not in engine._drawn


def test_rebuild_failure_keeps_the_drawn_widget(pmtiles_spec, monkeypatch):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(pmtiles_spec)
    before = engine.leaflet_layer(pmtiles_spec.id)
    monkeypatch.setattr(LeafletEngine, "_build", _failing_build)
    store.restyle(pmtiles_spec.id, stroke="#ff0000")  # a PMTiles restyle rebuilds
    assert store.view(pmtiles_spec.id).status == "error"
    assert engine.leaflet_layer(pmtiles_spec.id) is before and before in m.layers
    drawn_spec, drawn_render = engine._drawn[pmtiles_spec.id]
    assert drawn_spec.style.stroke is None and drawn_render.vector_style.stroke is None


def test_async_build_failure_is_handled(vector_spec, monkeypatch):
    monkeypatch.setattr(LeafletEngine, "_build", _failing_build)

    async def run():
        m, store = ipl.Map(), LayerStore()
        engine = LeafletEngine(m, store)
        store.add(vector_spec)
        tasks = list(engine._tasks)
        await engine.wait_idle()
        assert tasks and all(task.exception() is None for task in tasks)
        assert store.view(vector_spec.id).status == "error"
        assert engine.leaflet_layer(vector_spec.id) is None

    asyncio.run(run())


def test_theme_follow_attrs(vector_spec):
    store = LayerStore()
    engine = LeafletEngine(SepalMap(gee=False), store)
    store.add(vector_spec)
    assert set(engine.leaflet_layer(vector_spec.id).theme_style) == {True, False}


def test_close_detaches(raster_spec):
    m, store = ipl.Map(), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    engine.close()
    assert not any(getattr(lyr, "layer_id", None) for lyr in m.layers)


def test_layer_changes_are_one_at_a_time(raster_spec, vector_spec, pmtiles_spec):
    # SepalMap's LayerStateControl reads every change of m.layers as one added or removed layer
    m, store = ipl.Map(), LayerStore()
    LeafletEngine(m, store)
    sizes = []
    m.observe(lambda c: sizes.append(len(set(c["new"]) ^ set(c["old"]))), "layers")
    store.add(raster_spec)
    store.add(vector_spec)
    store.add(pmtiles_spec)
    store.move(raster_spec.id, 0)
    store.restyle(pmtiles_spec.id, stroke="#ff0000")
    store.set_visible(vector_spec.id, False)
    store.remove(raster_spec.id)
    assert sizes and set(sizes) == {1}


def test_state_bar_settles_after_reattaching_a_loading_layer(raster_spec, raster_spec_b):
    m, store = SepalMap(gee=False), LayerStore()
    engine = LeafletEngine(m, store)
    store.add(raster_spec)
    a = engine.leaflet_layer(raster_spec.id)
    a.set_trait("loading", True)
    store.add(raster_spec_b)
    b = engine.leaflet_layer(raster_spec_b.id)
    b.set_trait("loading", True)
    store.move(raster_spec.id, 0)  # both are detached and re-attached while still loading
    a.set_trait("loading", False)
    b.set_trait("loading", False)
    assert m.state.nb_loading_layer == 0
    assert m.state.loading is False

"""Tests for the LayerPanel, its rows and the basemap picker."""

import io
import shutil
import zipfile
from pathlib import Path

import solara

from pysepal.layers import LayerSpec, LayerStore
from pysepal.mapping import SepalMap
from pysepal.solara.components.layer_panel import LayerPanel
from pysepal.solara.components.layer_panel.download import download_payload
from tests.test_solara._layer_panel_helpers import (
    all_text,
    click,
    export_button,
    export_buttons,
    find_visibility_toggle,
    pick_basemap,
    row_ids,
)


def test_rows_follow_store_order(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert row_ids(box) == [raster_spec_b.id, raster_spec.id]


def test_toggle_hides_layer(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    find_visibility_toggle(box, raster_spec.id).fire_event("click", {})
    assert store.view(raster_spec.id).visible is False


def test_error_row_shows_message(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    store.set_status(raster_spec.id, "error", error="boom")
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert "boom" in all_text(box)


def test_empty_store_shows_empty_text():
    box, _ = solara.render(LayerPanel(store=LayerStore()), handle_error=False)
    assert "No layers" in all_text(box)


def test_export_only_for_gee_with_callback(raster_spec, gee_spec):
    exported, store = [], LayerStore()
    store.add(raster_spec)
    store.add(gee_spec)
    box, _ = solara.render(LayerPanel(store=store, on_export=exported.append), handle_error=False)
    assert export_buttons(box) == [gee_spec.id]
    click(export_button(box, gee_spec.id))
    assert exported == [store.get(gee_spec.id)]


def test_shapefile_download_zips_only_sidecars(fake_vector, tmp_path):
    for f in fake_vector.parent.glob(f"{fake_vector.stem}.*"):
        shutil.copy(f, tmp_path)
    (tmp_path / f"{fake_vector.stem}.csv").write_text("unrelated")
    data, name = download_payload(LayerSpec.from_vector(tmp_path / fake_vector.name))
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert name.endswith(".zip") and {".shp", ".shx", ".dbf"} <= {Path(n).suffix for n in names}
    assert not any(n.endswith(".csv") for n in names)


def test_basemap_picker_is_exclusive():
    m = SepalMap(gee=False, basemaps=["SEPAL_DARK", "OpenStreetMap"])
    box, _ = solara.render(LayerPanel(store=m.layer_store, map_=m), handle_error=False)
    pick_basemap(box, "OpenStreetMap")
    assert [lyr.visible for lyr in m.layers if lyr.base] == [False, True]
